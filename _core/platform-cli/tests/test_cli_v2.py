"""Тесты T10: subprocess-контур ``platform2`` — критерии выхода фазы P1 (§18.1).

Запускают установленный entry ``platform2`` **отдельным процессом**
(``subprocess.run`` через ``tests/fixtures/support.py``) из временных
директорий: без docker/сети/глобальных путей, окружение изолировано
(``make_env``: конфиг-env снят, ``XDG_CONFIG_HOME``/CWD в ``tmp_path``,
``NO_COLOR=1``/``PYTHONUTF8=1`` дефолтом, ``TERM``/``COLUMNS`` задаются явно),
таймаут 30 s — CI не виснет.

Соответствие критериев §18.1-P1 тестам:

=====================================  ========================================
Критерий                               Тесты
=====================================  ========================================
(а) help: exit 0, без заглушек, -h     ``TestHelp.*``
(б) exit codes 0/1/2/3/130             ``TestExitCodes.*``, ``TestSignals.*``
(в) текст → stderr, JSON → stdout,     ``TestChannels.*``
    ровно одна «Подсказка:»
(г) TTY / non-TTY, цвета               ``tests/test_tty.py``
(д) ``--json``-ошибки: объект,         ``TestJsonErrors.*``
    не массив
(е) опции в любой позиции (§7.4)       ``TestPositionInvariance.*``
(ж) golden 60/80/120 + ``NO_COLOR``    ``TestGolden.*``
=====================================  ========================================

Достижимость сценариев через ``platform2`` в P1: заглушки §7.5 ленивы
(``build_ctx`` не вызывают), поэтому настоящие ``invalid_value``/
``config_not_found``/``internal_error`` гоняются харнессом
``fixtures/boundary_cli.py`` тем же boundary ``run_app``; in-process-контур —
``test_boundary.py``/``test_ctx.py``/``test_config_v2.py``.

Известные отклонения приложения (зафиксированы в T10, исправлены в T11):

- ``platform2 -h`` был exit 2 «No such option: -h» — исправлено в T11
  (``create_app``: ``context_settings={"help_option_names": ["-h",
  "--help"]}``, §7.4);
- help (rich-рамка) адаптируется к ``COLUMNS`` (§12.1): сырые байты help при
  60/80/120 различаются; равенство по ширинам проверяется для
  width-независимого контракта (текст ошибки — ``TestGolden``) и в
  нормализованном виде для help.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from tests.fixtures.support import (
    FIXTURES_DIR,
    make_env,
    make_ops_project,
    normalize_help,
    run_fixture,
    run_platform2,
)

#: Заглушки §7.5 — не должны появляться в ``platform2 --help``.
STUB_NAMES: tuple[str, ...] = ("deploy", "stop", "restart", "logs", "backup", "new", "list", "reload", "status")

#: Golden-снапшоты (сгенерированы этим же контуром, см. ``tests/README.md``).
GOLDEN_DIR: Path = FIXTURES_DIR / "golden"

#: Ширины терминала для golden/детерминизма (§12.1, §18.2 п.4).
WIDTHS: tuple[str, ...] = ("60", "80", "120")


def cli(
    tmp_path: Path,
    *args: str,
    cwd: Path | None = None,
    overrides: Mapping[str, str | None] | None = None,
    binary: bool = False,
) -> subprocess.CompletedProcess:
    """``platform2 <args>`` отдельным процессом с изолированным окружением."""
    return run_platform2(args, cwd=cwd or tmp_path, env=make_env(tmp_path, overrides), binary=binary)


def harness(
    tmp_path: Path,
    script: str,
    *args: str,
    cwd: Path | None = None,
    overrides: Mapping[str, str | None] | None = None,
) -> subprocess.CompletedProcess:
    """Харнесс ``tests/fixtures/<script> <args>`` отдельным процессом."""
    return run_fixture(script, args, cwd=cwd or tmp_path, env=make_env(tmp_path, overrides))


class TestHelp:
    """(а) ``--help``: exit 0 без конфига, заглушки скрыты (§7.5, §18.1-P1)."""

    def test_help_exit_0_from_dir_without_config(self, tmp_path: Path) -> None:
        """Help работает в пустой директории без ``.ops-config.yml`` (Ctx ленив)."""
        result = cli(tmp_path, "--help")
        assert result.returncode == 0
        assert result.stderr == ""
        assert "Usage: platform2 [OPTIONS] COMMAND [ARGS]..." in result.stdout
        assert "Управление платформой" in result.stdout
        assert "\x1b" not in result.stdout  # NO_COLOR=1 в окружении прогона

    def test_help_does_not_list_legacy_stubs(self, tmp_path: Path) -> None:
        """Ни одна из 9 заглушек не попадает в help (секции Commands нет вовсе)."""
        result = cli(tmp_path, "--help")
        assert result.returncode == 0
        assert "Commands" not in result.stdout  # все 9 команд hidden (§7.5)

        # «Первое читаемое слово» строки (рамки rich пропускаются) — как в
        # test_legacy/test_ctx: имена заглушек не должны быть командами.
        first_tokens = {
            next(token for token in line.split() if any(ch.isalnum() for ch in token))
            for line in result.stdout.splitlines()
            if any(ch.isalnum() for ch in line)
        }
        assert set(STUB_NAMES) & first_tokens == set()

    def test_h_flag_equivalent_to_help(self, tmp_path: Path) -> None:
        short = cli(tmp_path, "-h")
        long = cli(tmp_path, "--help")
        assert short.returncode == 0
        assert short.stderr == ""
        assert short.stdout == long.stdout


class TestExitCodes:
    """(б) Таблица exit-кодов §12.4 реальными запусками отдельных процессов.

    0 — help/успех; 1 — неожиданное; 2 — заглушка/неизвестная команда/
    ``invalid_value``; 3 — ``config_not_found``; 130 — SIGINT (``TestSignals``).
    """

    def test_exit_0_valid_project_via_boundary_harness(self, tmp_path: Path) -> None:
        """Сборка Ctx в валидном tmp-проекте (маркер по CWD) → exit 0, без вывода."""
        project = make_ops_project(tmp_path / "proj")
        result = harness(tmp_path, "boundary_cli.py", "ctx", cwd=project)
        assert result.returncode == 0
        assert result.stdout == ""
        assert result.stderr == ""

    def test_exit_2_stub_command(self, tmp_path: Path) -> None:
        """Заглушка §7.5 → exit 2 (``command_moved``)."""
        result = cli(tmp_path, "deploy", "api")
        assert result.returncode == 2

    def test_exit_2_unknown_command(self, tmp_path: Path) -> None:
        """Неизвестная команда → exit 2 (``invalid_value``), текст в stderr."""
        result = cli(tmp_path, "nosuch")
        assert result.returncode == 2
        assert result.stdout == ""
        assert "No such command" in result.stderr

    def test_exit_2_project_dir_nonexistent_current_behavior(self, tmp_path: Path) -> None:
        """Фактическое поведение P1: ``--project-dir=/nonexistent`` на заглушке.

        Заглушки ленивы (``build_ctx`` не вызывается), поэтому config-слой не
        достигается и exit 2 приходит от ``command_moved``, а не от
        ``invalid_value``. Настоящий ``invalid_value`` —
        ``test_exit_2_invalid_value_via_boundary_harness``; in-process —
        ``test_config_v2.test_level1_project_dir_nonexistent_is_invalid_value``.

        Зафиксировано как допустимое в P1: перепроверено в T11 (бэклог
        T11 «интеграционное ревью», ленивый ``build_ctx`` — контракт T8/T9);
        архитектура ленивости не пересматривается (tech spec §11, принцип
        «help/заглушки без конфига»).
        """
        text = cli(tmp_path, "--project-dir=/nonexistent", "deploy", "api")
        assert text.returncode == 2
        assert "Команда изменена" in text.stderr

        payload = json.loads(cli(tmp_path, "--project-dir=/nonexistent", "deploy", "api", "--json").stdout)
        assert payload["error"]["code"] == "command_moved"  # НЕ invalid_value (см. докстринг)

    def test_exit_2_invalid_value_via_boundary_harness(self, tmp_path: Path) -> None:
        """Настоящий ``invalid_value`` (config-слой) → exit 2, текст в stderr."""
        result = harness(tmp_path, "boundary_cli.py", "ctx", "--project-dir", "/nonexistent-proj")
        assert result.returncode == 2
        assert result.stdout == ""
        assert "не является существующей директорией" in result.stderr
        assert "Подсказка: допустимые значения" in result.stderr  # hint §12.4
        assert "Traceback" not in result.stderr

    def test_exit_3_config_not_found_via_boundary_harness(self, tmp_path: Path) -> None:
        """``config_not_found`` → exit 3, текст в stderr, stdout пуст."""
        empty = tmp_path / "empty"
        empty.mkdir()
        result = harness(tmp_path, "boundary_cli.py", "ctx", "--project-dir", str(empty))
        assert result.returncode == 3
        assert result.stdout == ""
        assert "Конфиг не найден" in result.stderr
        assert "Traceback" not in result.stderr

    def test_exit_1_unexpected_without_traceback_by_default(self, tmp_path: Path) -> None:
        """Неожиданное исключение → exit 1, traceback только при ``--verbose``."""
        result = harness(tmp_path, "boundary_cli.py", "boom")
        assert result.returncode == 1
        assert result.stdout == ""
        assert "Непредвиденная ошибка: ValueError: boom" in result.stderr
        assert "Traceback" not in result.stderr

    def test_exit_1_unexpected_traceback_with_verbose(self, tmp_path: Path) -> None:
        result = harness(tmp_path, "boundary_cli.py", "--verbose", "boom")
        assert result.returncode == 1
        assert result.stdout == ""
        assert "Traceback" in result.stderr
        assert "ValueError: boom" in result.stderr


class TestChannels:
    """(в) Разделение каналов §12.1/§12.2: текст → stderr, JSON → stdout."""

    def test_stub_text_error_to_stderr_stdout_empty(self, tmp_path: Path) -> None:
        result = cli(tmp_path, "deploy", "api")
        assert result.returncode == 2
        assert result.stdout == ""  # текст — только stderr
        assert "Команда изменена в platform v2." in result.stderr
        assert "Было: platform deploy api" in result.stderr
        assert "Стало: platform service deploy api" in result.stderr
        assert result.stderr.count("Подсказка:") == 1  # ровно одна подсказка
        assert "Traceback" not in result.stderr

    def test_stub_json_error_to_stdout_stderr_empty(self, tmp_path: Path) -> None:
        result = cli(tmp_path, "deploy", "api", "--json")
        assert result.returncode == 2
        assert result.stderr == ""  # JSON — только stdout
        payload = json.loads(result.stdout)
        assert payload["schema_version"] == 1
        assert payload["error"]["code"] == "command_moved"
        assert payload["error"]["object"] == "deploy api"
        assert payload["error"]["hint"] == "platform --help; заглушки будут удалены в v2.1"
        assert "Подсказка:" not in payload["error"]["message"]

    def test_unknown_command_text_error_to_stderr(self, tmp_path: Path) -> None:
        result = cli(tmp_path, "nosuch")
        assert result.returncode == 2
        assert result.stdout == ""
        assert "No such command 'nosuch'." in result.stderr
        assert result.stderr.count("Подсказка:") == 1
        assert "Traceback" not in result.stderr


class TestJsonErrors:
    """(д) ``--json``-ошибки: всегда объект ``schema_version`` в stdout (§12.2)."""

    @pytest.mark.parametrize(
        ("args", "code"),
        [(["deploy", "api"], "command_moved"), (["nosuch"], "invalid_value")],
        ids=["stub", "unknown-command"],
    )
    def test_json_error_is_object_in_stdout(self, tmp_path: Path, args: list[str], code: str) -> None:
        result = cli(tmp_path, *args, "--json")
        assert result.returncode == 2  # exit-код сохраняется
        assert result.stderr == ""
        payload = json.loads(result.stdout)
        assert isinstance(payload, dict)  # никогда не массив и не смешанный поток
        assert payload["schema_version"] == 1
        assert payload["error"]["code"] == code
        for field in ("code", "message", "object", "hint"):
            assert field in payload["error"]

    def test_invalid_value_json_via_boundary_harness(self, tmp_path: Path) -> None:
        result = harness(tmp_path, "boundary_cli.py", "ctx", "--project-dir", "/nonexistent-proj", "--json")
        assert result.returncode == 2
        assert result.stderr == ""
        payload = json.loads(result.stdout)
        assert isinstance(payload, dict)
        assert payload["schema_version"] == 1
        assert payload["error"]["code"] == "invalid_value"
        assert payload["error"]["hint"] is not None

    def test_config_not_found_json_via_boundary_harness(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        result = harness(tmp_path, "boundary_cli.py", "ctx", "--project-dir", str(empty), "--json")
        assert result.returncode == 3
        assert result.stderr == ""
        payload = json.loads(result.stdout)
        assert isinstance(payload, dict)
        assert payload["schema_version"] == 1
        assert payload["error"]["code"] == "config_not_found"


class TestPositionInvariance:
    """(е) Общие опции §7.4 в любой позиции — через реальный entry."""

    def test_json_forms_are_byte_identical(self, tmp_path: Path) -> None:
        """``deploy api --json`` ≡ ``--json deploy api`` ≡ ``--json deploy --verbose api``."""
        forms: Sequence[tuple[str, ...]] = (
            ("deploy", "api", "--json"),
            ("--json", "deploy", "api"),
            ("--json", "deploy", "--verbose", "api"),
        )
        results = [cli(tmp_path, *form, binary=True) for form in forms]
        assert {result.returncode for result in results} == {2}
        # stdout-JSON побайтово идентичен во всех трёх позициях опции.
        assert results[0].stdout == results[1].stdout == results[2].stdout
        # ``--verbose`` добавляет traceback — но только в stderr (§12.3):
        # JSON-контракт stdout при этом не меняется.
        assert results[0].stderr == b""
        assert results[1].stderr == b""
        assert b"Traceback" in results[2].stderr

    def test_project_dir_before_subcommand_accepted(self, tmp_path: Path) -> None:
        """``platform2 --project-dir <path> deploy api`` — заглушке всё равно (exit 2)."""
        project = make_ops_project(tmp_path / "proj")
        result = cli(tmp_path, "--project-dir", str(project), "deploy", "api")
        assert result.returncode == 2
        assert "Было: platform deploy api" in result.stderr


class TestGolden:
    """(ж) Golden-снапшоты: ширина 60/80/120, ``NO_COLOR``, детерминизм (§18.2)."""

    def test_stub_error_width_independent_and_matches_golden(self, tmp_path: Path) -> None:
        """Текст ошибки заглушки не зависит от ``COLUMNS`` и равен golden."""
        outputs = [cli(tmp_path, "deploy", "api", overrides={"COLUMNS": width}).stderr for width in WIDTHS]
        outputs.append(cli(tmp_path, "deploy", "api").stderr)  # дефолт subprocess (80)
        golden = (GOLDEN_DIR / "stub_error.txt").read_text(encoding="utf-8")
        assert outputs[0] == outputs[1] == outputs[2] == outputs[3] == golden
        assert "\x1b" not in outputs[0]  # NO_COLOR=1 во всех golden-прогонах

    def test_help_matches_golden_at_default_width(self, tmp_path: Path) -> None:
        """Точный снапшот help при дефолтной ширине (COLUMNS снят → 80)."""
        result = cli(tmp_path, "--help")
        assert result.stdout == (GOLDEN_DIR / "help.txt").read_text(encoding="utf-8")
        assert result.stderr == ""

    def test_help_deterministic_within_each_width(self, tmp_path: Path) -> None:
        """Детерминизм: два прогона при одной ширине дают идентичный help."""
        for width in WIDTHS:
            overrides = {"COLUMNS": width}
            assert (
                cli(tmp_path, "--help", overrides=overrides).stdout
                == cli(tmp_path, "--help", overrides=overrides).stdout
            )

    def test_help_normalized_content_independent_of_width(self, tmp_path: Path) -> None:
        """Содержимое help (без рамок rich) не зависит от ширины.

        Сырые байты help при 60/80/120 различаются — rich-рамка адаптируется
        к ``COLUMNS`` (§12.1, это поведение, а не баг); равенство фиксируется
        в нормализованном виде, сырая равность — на width-независимом
        контракте (текст ошибки, см. ``test_stub_error_width_independent…``).
        """
        normalized = {normalize_help(cli(tmp_path, "--help", overrides={"COLUMNS": width}).stdout) for width in WIDTHS}
        assert len(normalized) == 1


class TestSignals:
    """130: реальный SIGINT висящей команде через boundary (§12.4, §12.5)."""

    def test_sigint_during_command_exits_130_without_traceback(self, tmp_path: Path) -> None:
        """SIGINT после маркера готовности → exit 130, stderr без traceback.

        Детерминированность: харнесс пишет маркер **внутри** команды (уже в
        ``run_app``); сигнал шлётся только после маркера, таймауты везде.
        """
        marker = tmp_path / "ready"
        proc = subprocess.Popen(  # noqa: S603 — свой харнесс, без shell
            [sys.executable, str(FIXTURES_DIR / "hang_cli.py"), str(marker)],
            cwd=tmp_path,
            env=make_env(tmp_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
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
                pytest.fail(f"харнесс не дошёл до hang-команды (exit={proc.returncode}): {out!r} {err!r}")

            proc.send_signal(signal.SIGINT)
            stdout, stderr = proc.communicate(timeout=30.0)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()

        assert proc.returncode == 130
        assert stdout == ""
        assert "прервана по Ctrl-C" in stderr
        assert "Traceback" not in stderr
