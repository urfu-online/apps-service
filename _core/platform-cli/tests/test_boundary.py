"""Тесты T9: единый exception boundary и маршрутизация вывода (tech spec §5/§6).

Покрывают критерии приёмки T9 (бэклог T9, спека §12.1–§12.5):

- таблица «сценарий → exit / канал / формат»:

  ==========================================  ======  ==========================
  Сценарий                                    exit    Канал / формат
  ==========================================  ======  ==========================
  заглушка, text (``platform2 deploy api``)   2       stderr, stdout пуст
  заглушка, json (``--json``)                 2       stdout-объект schema_version=1, stderr пуст
  неожиданное исключение                      1       stderr, traceback только при ``--verbose``
  ``config_not_found`` через ``build_ctx``    3       stderr, stdout пуст (без traceback)
  Ctrl-C                                      130     stderr, traceback никогда
  ==========================================  ======  ==========================

- Ctrl-C: in-process ``KeyboardInterrupt`` внутри boundary **и** реальный
  subprocess с SIGINT во время висящей команды → exit 130 без traceback;
- секреты (§16): ``PLATFORM_API_TOKEN`` не попадает ни в stdout/stderr, ни в
  traceback; ``repr(AppConfig)`` токен скрывает;
- каналы не смешиваются: текст-ошибка → пустой stdout, JSON → пустой stderr;
- фолбэк-рендер ``cli._fallback_emit`` (ошибки до сборки реестра) — тот же
  JSON/текст-контракт.

Патчи внутренних имён v2 запрещены (§10.6): команды-заглушки строятся через
конструкторы (``run_app``/``build_ctx``), фолбэк вызывается напрямую.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest
import typer

from apps_platform.cli import GlobalOpts, _fallback_emit, build_ctx, main, run_app
from apps_platform.config import AppConfig, make_app_config
from apps_platform.core.errors import PlatformError, wrap_unexpected

#: Секрет §16/§11.1: не должен появиться ни в одном потоке boundary.
_SECRET_TOKEN = "s3kr3t-platform-api-token-DO-NOT-PRINT"

# Драйвер subprocess-теста Ctrl-C: команда пишет маркер готовности и висит;
# SIGINT приходит, пока она уже выполняется внутри run_app → boundary (T9).
_HANG_DRIVER = '''
"""Висящая команда: маркер готовности, затем сон до SIGINT (boundary T9)."""

import sys
import time
from pathlib import Path

import typer

from apps_platform.cli import GlobalOpts, run_app

marker = Path(sys.argv[1])
app = typer.Typer(add_completion=False)


@app.command()
def hang() -> None:
    """Пишет маркер и висит до SIGINT — boundary должен дать exit 130."""
    marker.write_text("ready", encoding="utf-8")
    time.sleep(60)


@app.command()
def noop() -> None:
    """Вторая команда — чтобы Typer собрал группу, а не single-command app."""


raise SystemExit(run_app(app, ["hang"], GlobalOpts()))
'''


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Чистое окружение конфига (как в test_ctx/test_config_v2)."""
    for var in (
        "OPS_PROJECT_ROOT",
        "OPS_CONFIG_PATH",
        "PLATFORM_ENV",
        "PLATFORM_SSL_VERIFY",
        "PLATFORM_API_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


def app_with(*, run: Callable[[], None]) -> typer.Typer:
    """Приложение для boundary-тестов: тестируемая команда ``run`` + ``noop``.

    Вторая команда обязательна: Typer сворачивает app с единственной командой
    в ``click.Command`` без подкоманд (имя команды в argv не принимается).
    """
    app = typer.Typer(add_completion=False)
    app.command(name="run")(run)

    @app.command(name="noop")
    def noop() -> None:
        """Вторая команда — чтобы Typer собрал группу."""

    return app


class TestScenarioTable:
    """Таблица «сценарий → exit / канал / формат» (критерий T9)."""

    def test_stub_text_error_stderr_exit_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(["deploy", "api"])
        captured = capsys.readouterr()
        assert code == 2
        assert captured.out == ""  # текст → только stderr (§12.1)
        assert "Команда изменена в platform v2." in captured.err
        assert "Было: platform deploy api" in captured.err
        assert captured.err.count("Подсказка:") == 1  # без двойного hint (T8→T9)
        assert "Traceback" not in captured.err

    def test_stub_json_error_stdout_exit_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(["deploy", "api", "--json"])
        captured = capsys.readouterr()
        assert code == 2
        assert captured.err == ""  # JSON → только stdout (§12.2)
        payload = json.loads(captured.out)
        assert payload["schema_version"] == 1
        assert payload["error"]["code"] == "command_moved"
        assert payload["error"]["object"] == "deploy api"

    @pytest.mark.parametrize("verbose", [False, True], ids=["no-verbose", "verbose"])
    def test_unexpected_exit_1_traceback_only_with_verbose(
        self, verbose: bool, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def kaboom() -> None:
            """Бросает неожиданное исключение."""
            raise ValueError("boom")

        code = run_app(app_with(run=kaboom), ["run"], GlobalOpts(verbose=verbose))
        captured = capsys.readouterr()
        assert code == 1
        assert captured.out == ""
        assert "Непредвиденная ошибка: ValueError: boom" in captured.err
        assert ("Traceback" in captured.err) is verbose
        if verbose:
            assert "ValueError: boom" in captured.err  # traceback включает cause

    def test_config_not_found_via_build_ctx_exit_3(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()

        def go() -> None:
            """Лениво собирает Ctx без ops-конфига."""
            build_ctx(GlobalOpts(project_dir=empty), system_config_paths=())

        code = run_app(app_with(run=go), ["run"], GlobalOpts(project_dir=empty))
        captured = capsys.readouterr()
        assert code == 3
        assert captured.out == ""
        assert "Конфиг не найден" in captured.err
        assert "Traceback" not in captured.err

    def test_usage_error_exit_2_invalid_value(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(["nosuch"])
        captured = capsys.readouterr()
        assert code == 2
        assert captured.out == ""
        assert "No such command" in captured.err
        assert "Traceback" not in captured.err


class TestKeyboardInterrupt:
    """Ctrl-C → ``cancelled`` (exit 130) без traceback (§12.5, критерий T9)."""

    def test_inprocess_exit_130_no_traceback(self, capsys: pytest.CaptureFixture[str]) -> None:
        def interrupted() -> None:
            """Имитирует Ctrl-C внутри boundary."""
            raise KeyboardInterrupt

        code = run_app(app_with(run=interrupted), ["run"], GlobalOpts())
        captured = capsys.readouterr()
        assert code == 130
        assert captured.out == ""
        assert "прервана по Ctrl-C" in captured.err
        assert "Traceback" not in captured.err

    def test_inprocess_verbose_still_no_traceback(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Даже с ``--verbose`` прерывание не печатает traceback."""

        def interrupted() -> None:
            """Имитирует Ctrl-C внутри boundary."""
            raise KeyboardInterrupt

        code = run_app(app_with(run=interrupted), ["run"], GlobalOpts(verbose=True))
        captured = capsys.readouterr()
        assert code == 130
        assert "Traceback" not in captured.err

    def test_inprocess_json_error_in_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        def interrupted() -> None:
            """Имитирует Ctrl-C в json-режиме."""
            raise KeyboardInterrupt

        code = run_app(app_with(run=interrupted), ["run"], GlobalOpts(json=True))
        captured = capsys.readouterr()
        assert code == 130
        assert captured.err == ""
        payload = json.loads(captured.out)
        assert payload["schema_version"] == 1
        assert payload["error"]["code"] == "cancelled"

    def test_sigint_subprocess_during_command_exit_130(self, tmp_path: Path) -> None:
        """Реальный SIGINT висящей команде → exit 130, stderr без traceback.

        Детерминированность: драйвер пишет маркер-файл **внутри** команды
        (т.е. уже внутри ``run_app``); тест шлёт SIGINT только после маркера.
        """
        driver = tmp_path / "hang_driver.py"
        driver.write_text(_HANG_DRIVER, encoding="utf-8")
        marker = tmp_path / "ready"

        proc = subprocess.Popen(  # noqa: S603 — собственный драйвер, без shell
            [sys.executable, str(driver), str(marker)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=tmp_path,
        )
        try:
            deadline = time.monotonic() + 15.0
            ready = False
            while time.monotonic() < deadline:
                if marker.exists():
                    ready = True
                    break
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
            if not ready:
                out, err = proc.communicate()
                pytest.fail(f"драйвер не добрался до висящей команды (exit={proc.returncode}): {out!r} {err!r}")

            proc.send_signal(signal.SIGINT)
            stdout, stderr = proc.communicate(timeout=15.0)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()

        assert proc.returncode == 130
        assert stdout == ""
        assert "прервана по Ctrl-C" in stderr
        assert "Traceback" not in stderr


class TestNoSecrets:
    """§16: ``PLATFORM_API_TOKEN`` не течёт ни в один поток boundary."""

    @pytest.fixture(autouse=True)
    def _with_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PLATFORM_API_TOKEN", _SECRET_TOKEN)

    def test_stub_text_error_hides_token(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(["deploy", "api"])
        captured = capsys.readouterr()
        assert code == 2
        assert _SECRET_TOKEN not in captured.out
        assert _SECRET_TOKEN not in captured.err

    def test_stub_json_error_hides_token(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(["deploy", "api", "--json"])
        captured = capsys.readouterr()
        assert code == 2
        assert _SECRET_TOKEN not in captured.out
        assert _SECRET_TOKEN not in captured.err

    def test_unexpected_verbose_traceback_hides_token(self, capsys: pytest.CaptureFixture[str]) -> None:
        def kaboom() -> None:
            """Бросает неожиданное исключение — traceback не должен содержать токен."""
            raise ValueError("boom")

        code = run_app(app_with(run=kaboom), ["run"], GlobalOpts(verbose=True))
        captured = capsys.readouterr()
        assert code == 1
        assert "Traceback" in captured.err
        assert _SECRET_TOKEN not in captured.out
        assert _SECRET_TOKEN not in captured.err

    def test_config_not_found_hides_token(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()

        def go() -> None:
            """Собирает Ctx без конфига при установленном токене."""
            build_ctx(GlobalOpts(project_dir=empty), system_config_paths=())

        code = run_app(app_with(run=go), ["run"], GlobalOpts(project_dir=empty))
        captured = capsys.readouterr()
        assert code == 3
        assert _SECRET_TOKEN not in captured.out
        assert _SECRET_TOKEN not in captured.err

    def test_app_config_repr_hides_token(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        (project / ".ops-config.yml").write_text("master_url: http://master.test\n", encoding="utf-8")

        cfg = make_app_config(project_dir=project, system_config_paths=())
        assert isinstance(cfg, AppConfig)
        assert cfg.api_token == _SECRET_TOKEN
        assert _SECRET_TOKEN not in repr(cfg)
        assert _SECRET_TOKEN not in str(cfg)


class TestFallbackRender:
    """``_fallback_emit`` — контракт каналов до сборки реестра (T9)."""

    def test_text_contract_stderr_exit_from_registry(self, capsys: pytest.CaptureFixture[str]) -> None:
        error = PlatformError(code="config_not_found", message="Конфиг не найден.", object="/nope/.ops-config.yml")
        code = _fallback_emit(error, GlobalOpts())
        captured = capsys.readouterr()
        assert code == 3  # exit — только из реестра §12.4
        assert captured.out == ""
        assert "✘ Конфиг не найден." in captured.err
        assert "Объект: /nope/.ops-config.yml" in captured.err
        assert "Подсказка:" in captured.err
        assert "Traceback" not in captured.err

    def test_json_contract_stdout_exit_from_registry(self, capsys: pytest.CaptureFixture[str]) -> None:
        error = PlatformError(code="config_not_found", message="Конфиг не найден.")
        code = _fallback_emit(error, GlobalOpts(json=True))
        captured = capsys.readouterr()
        assert code == 3
        assert captured.err == ""
        payload = json.loads(captured.out)
        assert payload["schema_version"] == 1
        assert payload["error"]["code"] == "config_not_found"
        assert payload["error"]["hint"] is not None

    def test_unexpected_wrapped_to_exit_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = _fallback_emit(wrap_unexpected(RuntimeError("kaboom")), GlobalOpts())
        captured = capsys.readouterr()
        assert code == 1
        assert "Непредвиденная ошибка: RuntimeError: kaboom" in captured.err
        assert "Traceback" not in captured.err

    def test_verbose_prints_traceback_to_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        try:
            raise ValueError("boom")
        except ValueError as exc:
            error = wrap_unexpected(exc)  # cause — реально брошенное исключение
        code = _fallback_emit(error, GlobalOpts(verbose=True))
        captured = capsys.readouterr()
        assert code == 1
        assert "Traceback" in captured.err
        assert "ValueError: boom" in captured.err
        assert captured.out == ""

    def test_cancelled_never_prints_traceback(self, capsys: pytest.CaptureFixture[str]) -> None:
        from apps_platform.core.errors import cancelled

        code = _fallback_emit(cancelled(), GlobalOpts(verbose=True))
        captured = capsys.readouterr()
        assert code == 130
        assert "прервана по Ctrl-C" in captured.err
        assert "Traceback" not in captured.err
