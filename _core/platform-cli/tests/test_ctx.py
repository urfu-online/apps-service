"""Тесты T8: ``apps_platform/cli.py`` — общие опции, Ctx/build_ctx, boundary.

Критерии приёмки T8 (бэклог, tech spec §3/§5/§6/§10):

- :func:`extract_global_opts` — позиционная инвариантность общих опций §7.4,
  ``--project-dir`` в двух формах, ``--json`` → ``no_input``, остаток argv
  не трогается; чистая функция, без Typer;
- :func:`build_ctx` — composition root: fake-адаптеры через конструктор
  (не патчи), ``Ctx`` frozen, поля — runtime_checkable-порты ``core.ports``;
  отсутствие ops-конфига → ``PlatformError(config_not_found)`` exit 3;
  отсутствие рендерера → ``AssertionError`` при сборке;
- boundary :func:`run_app`/:func:`main` — ``--help`` exit 0 без конфига,
  заглушки скрыты, ``PlatformError`` → exit 2 (не 1: frozen-обход больше
  не нужен после фикса ``core/errors.py``), неожиданное → exit 1
  (traceback только при ``--verbose``), ``--json`` ошибки в stdout.

Только конструкторы/параметры — патчи внутренних имён v2 запрещены (§10.6).
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import typer
from typer.core import TyperGroup
from typer.testing import CliRunner

from apps_platform.cli import (
    Ctx,
    GlobalOpts,
    build_ctx,
    create_app,
    extract_global_opts,
    main,
    run_app,
)
from apps_platform.commands.legacy import LEGACY_MOVES
from apps_platform.config import AppConfig
from apps_platform.core import ports
from apps_platform.core.errors import PlatformError
from apps_platform.core.models import DeadlinePolicy
from apps_platform.ui.renderers import get as get_renderer


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Чистое окружение конфига (как в test_config_v2): env снят, user config в tmp."""
    for var in (
        "OPS_PROJECT_ROOT",
        "OPS_CONFIG_PATH",
        "PLATFORM_ENV",
        "PLATFORM_SSL_VERIFY",
        "PLATFORM_API_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Валидный проект: ``--project-dir`` указывает сюда, ops-конфиг есть."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".ops-config.yml").write_text("master_url: http://master.test\n", encoding="utf-8")
    return root


# --- fake-адаптеры (подмена портов через конструктор Ctx, принцип §10.6) ------


class FakeDiscovery:
    def list_services(self) -> list[object]:
        return []


class FakeDocker:
    def inspect(self, service: str) -> object:
        return None


class FakeCaddy:
    def routes(self) -> object:
        return None


class FakeMaster:
    def info(self) -> object:
        return None


class FakeProber:
    def probe(self, service: str) -> object:
        return None


class FakeLocks:
    def acquire(self, key: str) -> object:
        return None


class FakeCache:
    def get(self, key: str) -> object:
        return None


class FakeJournal:
    def record(self, event: str) -> object:
        return None


class _Unregistered:
    """Тип без рендерера — для проверки AssertionError реестра."""


def _app_with(*, run: Callable[[], None]) -> typer.Typer:
    """Приложение для boundary-тестов: тестируемая команда ``run`` + ``noop``.

    Вторая команда обязательна: Typer сворачивает app с единственной командой
    в ``click.Command`` без подкоманд (тогда имя команды в argv не принимается).
    """
    app = typer.Typer(add_completion=False)
    app.command(name="run")(run)

    @app.command(name="noop")
    def noop() -> None:
        """Вторая команда — чтобы Typer собрал группу."""

    return app


class TestExtractGlobalOpts:
    """Чистая предобработка argv: общие опции §7.4 в любой позиции."""

    def test_defaults_and_remainder_is_input(self) -> None:
        opts, remainder = extract_global_opts(["deploy", "api"])
        assert opts == GlobalOpts()
        assert remainder == ["deploy", "api"]

    @pytest.mark.parametrize("position", [0, 1, 2])
    def test_flag_position_invariance(self, position: int) -> None:
        """``--json`` до/после подкоманды даёт одинаковый opts и остаток."""
        argv = ["deploy", "api"]
        argv.insert(position, "--json")
        opts, remainder = extract_global_opts(argv)
        assert opts.json is True
        assert opts.no_input is True
        assert remainder == ["deploy", "api"]

    def test_every_bool_flag_is_extracted(self) -> None:
        opts, remainder = extract_global_opts(["--verbose", "status", "--no-input", "--yes", "x", "--no-color"])
        assert opts.verbose is True
        assert opts.no_input is True
        assert opts.yes is True
        assert opts.no_color is True
        assert opts.json is False
        assert remainder == ["status", "x"]

    def test_json_implies_no_input(self) -> None:
        opts, _ = extract_global_opts(["--json"])
        assert opts.json is True
        assert opts.no_input is True

    def test_no_input_alone_does_not_set_json(self) -> None:
        opts, _ = extract_global_opts(["--no-input"])
        assert opts.no_input is True
        assert opts.json is False

    @pytest.mark.parametrize(
        "argv",
        [["--project-dir", "/srv/p"], ["deploy", "--project-dir", "/srv/p"], ["--project-dir=/srv/p"]],
        ids=["standalone", "after-subcommand", "equals-form"],
    )
    def test_project_dir_forms_value_consumed(self, argv: list[str]) -> None:
        opts, remainder = extract_global_opts(argv)
        assert opts.project_dir == Path("/srv/p")
        assert "/srv/p" not in remainder
        assert "--project-dir" not in remainder

    def test_unknown_options_and_positionals_untouched(self) -> None:
        argv = ["deploy", "--build", "--jsonx", "-x", "--project-dir-extra", "api"]
        opts, remainder = extract_global_opts(argv)
        assert opts == GlobalOpts()
        assert remainder == argv

    def test_remainder_preserves_relative_order(self) -> None:
        opts, remainder = extract_global_opts(["--verbose", "logs", "api", "--lines", "100", "--json"])
        assert opts.verbose is True and opts.json is True
        assert remainder == ["logs", "api", "--lines", "100"]

    def test_project_dir_without_value_left_for_typer(self) -> None:
        """Флаг без значения остаётся в остатке — сообщит Typer (exit 2)."""
        opts, remainder = extract_global_opts(["--project-dir"])
        assert opts.project_dir is None
        assert remainder == ["--project-dir"]

    def test_global_opts_is_frozen(self) -> None:
        opts = GlobalOpts()
        with pytest.raises(FrozenInstanceError):
            opts.json = True  # type: ignore[misc]


class TestBuildContext:
    """``build_ctx`` — composition root: адаптеры, порты, конфиг, реестр."""

    def test_builds_with_real_adapters_satisfying_ports(self, project: Path) -> None:
        opts = GlobalOpts(project_dir=project)
        ctx = build_ctx(opts, system_config_paths=())

        assert isinstance(ctx, Ctx)
        assert isinstance(ctx.config, AppConfig)
        assert ctx.root == project
        assert ctx.config.root == project
        assert ctx.global_opts == opts
        assert ctx.deadline_policy == DeadlinePolicy(budget_s=2.0)
        assert isinstance(ctx.discovery, ports.ServiceDiscovery)
        assert isinstance(ctx.docker, ports.DockerReader)
        assert isinstance(ctx.caddy, ports.CaddyReader)
        assert isinstance(ctx.master, ports.MasterGateway)
        assert isinstance(ctx.prober, ports.HealthProber)
        assert isinstance(ctx.locks, ports.LockManager)
        assert isinstance(ctx.cache, ports.CacheStore)
        assert isinstance(ctx.journal, ports.Journal)
        assert PlatformError in ctx.renderers

    def test_ctx_is_frozen(self, project: Path) -> None:
        ctx = build_ctx(GlobalOpts(project_dir=project), system_config_paths=())
        with pytest.raises(FrozenInstanceError):
            ctx.root = Path("/elsewhere")  # type: ignore[misc]

    def test_fake_adapters_override_via_constructor(self, project: Path) -> None:
        fake_discovery, fake_journal = FakeDiscovery(), FakeJournal()
        ctx = build_ctx(
            GlobalOpts(project_dir=project),
            adapters={"discovery": fake_discovery, "journal": fake_journal},
            system_config_paths=(),
        )
        assert ctx.discovery is fake_discovery
        assert ctx.journal is fake_journal
        assert isinstance(ctx.discovery, ports.ServiceDiscovery)
        assert isinstance(ctx.journal, ports.Journal)

    def test_unknown_adapter_name_is_assertion_error(self, project: Path) -> None:
        with pytest.raises(AssertionError, match="неизвестные адаптеры"):
            build_ctx(
                GlobalOpts(project_dir=project),
                adapters={"discovery": FakeDiscovery(), "disocery": FakeDiscovery()},
                system_config_paths=(),
            )

    def test_adapter_without_port_is_assertion_error(self, project: Path) -> None:
        with pytest.raises(AssertionError, match="не реализует порт"):
            build_ctx(
                GlobalOpts(project_dir=project),
                adapters={"discovery": object()},
                system_config_paths=(),
            )

    def test_config_not_found_raises_exit_3(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(PlatformError) as excinfo:
            build_ctx(GlobalOpts(project_dir=empty), system_config_paths=())
        assert excinfo.value.code == "config_not_found"
        assert excinfo.value.exit_code == 3

    def test_missing_renderer_assertion_at_build(self, project: Path) -> None:
        with pytest.raises(AssertionError, match="рендерера для PlatformError"):
            build_ctx(GlobalOpts(project_dir=project), renderers={}, system_config_paths=())

    def test_registry_get_unregistered_type_is_assertion_error(self) -> None:
        with pytest.raises(AssertionError, match="_Unregistered"):
            get_renderer(_Unregistered)

    def test_deadline_policy_from_user_prefs(self, project: Path, tmp_path: Path) -> None:
        xdg = tmp_path / "xdg"
        (xdg / "platform").mkdir(parents=True)
        (xdg / "platform" / "config.yml").write_text("status:\n  deadline: 5s\n", encoding="utf-8")
        ctx = build_ctx(GlobalOpts(project_dir=project), system_config_paths=())
        assert ctx.deadline_policy == DeadlinePolicy(budget_s=5.0)


class TestBoundary:
    """Exception boundary: каналы, exit-коды из реестра §12.4, скрытые заглушки."""

    def test_help_exit_0_without_ops_config(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """``--help`` работает без ``.ops-config.yml`` в CWD (Ctx не собирается)."""
        workdir = tmp_path / "no-config"
        workdir.mkdir()
        old_cwd = os.getcwd()
        try:
            os.chdir(workdir)
            code = main(["--help"])
        finally:
            os.chdir(old_cwd)
        captured = capsys.readouterr()
        assert code == 0
        assert "Заглушка" not in captured.out
        assert captured.err == ""

    def test_help_does_not_list_stubs(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(["--help"])
        output = capsys.readouterr().out
        assert code == 0

        # «Первое читаемое слово» строки (рамки rich пропускаются): имена
        # заглушек не должны встречаться как команды (как в test_legacy).
        first_tokens = {
            next(token for token in line.split() if any(ch.isalnum() for ch in token))
            for line in output.splitlines()
            if any(ch.isalnum() for ch in line)
        }
        assert set(LEGACY_MOVES) & first_tokens == set()

    def test_all_nine_stubs_registered_hidden(self) -> None:
        group = typer.main.get_command(create_app())
        assert isinstance(group, TyperGroup)
        assert set(group.commands) == set(LEGACY_MOVES)
        for name in LEGACY_MOVES:
            assert group.commands[name].hidden is True

    def test_stub_error_propagates_as_platform_error_not_frozen(self) -> None:
        """CliRunner: заглушка бросает PlatformError (не FrozenInstanceError, exit 2)."""
        result = CliRunner().invoke(create_app(), ["deploy", "api"], catch_exceptions=True)
        assert isinstance(result.exception, PlatformError)
        assert not isinstance(result.exception, FrozenInstanceError)
        assert result.exception.exit_code == 2

    def test_stub_text_error_to_stderr_exit_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(["deploy", "api"])
        captured = capsys.readouterr()
        assert code == 2
        assert captured.out == ""
        assert "Команда изменена в platform v2." in captured.err
        assert "Было: platform deploy api" in captured.err
        assert "Стало: platform service deploy api" in captured.err
        assert "Traceback" not in captured.err

    def test_stub_json_error_to_stdout_exit_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(["deploy", "api", "--json"])
        captured = capsys.readouterr()
        assert code == 2
        assert captured.err == ""
        payload = json.loads(captured.out)
        assert payload["schema_version"] == 1
        assert payload["error"]["code"] == "command_moved"
        assert "Было: platform deploy api" in payload["error"]["message"]

    def test_global_option_position_equivalence_end_to_end(self, capsys: pytest.CaptureFixture[str]) -> None:
        """``platform2 list --json`` и ``platform2 --json list`` эквивалентны."""
        code_before, out_before = main(["--json", "list"]), capsys.readouterr().out
        code_after, out_after = main(["list", "--json"]), capsys.readouterr().out
        assert code_before == code_after == 2
        assert out_before == out_after
        assert json.loads(out_before)["error"]["code"] == "command_moved"

    def test_platform_error_from_command_exit_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Платформенная ошибка из команды → exit 2 из реестра, не internal_error."""

        def boom() -> None:
            """Бросает PlatformError."""
            raise PlatformError(code="service_not_found", message="Сервис 'api' не найден", object="api")

        code = run_app(_app_with(run=boom), ["run"], GlobalOpts())
        captured = capsys.readouterr()
        assert code == 2
        assert "Сервис 'api' не найден" in captured.err
        assert "internal_error" not in captured.err
        assert "Traceback" not in captured.err
        assert captured.out == ""

    def test_config_not_found_from_command_exit_3(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()

        def go() -> None:
            """Лениво собирает Ctx без конфига."""
            build_ctx(GlobalOpts(project_dir=empty), system_config_paths=())

        code = run_app(_app_with(run=go), ["run"], GlobalOpts(project_dir=empty))
        captured = capsys.readouterr()
        assert code == 3
        assert "Конфиг не найден" in captured.err
        assert captured.out == ""
        assert "Traceback" not in captured.err

    def test_unexpected_exception_exit_1_without_traceback(self, capsys: pytest.CaptureFixture[str]) -> None:
        def kaboom() -> None:
            """Бросает неожиданное исключение."""
            raise ValueError("boom")

        code = run_app(_app_with(run=kaboom), ["run"], GlobalOpts())
        captured = capsys.readouterr()
        assert code == 1
        assert "Непредвиденная ошибка: ValueError: boom" in captured.err
        assert "Traceback" not in captured.err
        assert captured.out == ""

    def test_unexpected_exception_traceback_only_with_verbose(self, capsys: pytest.CaptureFixture[str]) -> None:
        def kaboom() -> None:
            """Бросает неожиданное исключение."""
            raise ValueError("boom")

        code = run_app(_app_with(run=kaboom), ["run"], GlobalOpts(verbose=True))
        captured = capsys.readouterr()
        assert code == 1
        assert "Traceback" in captured.err
        assert "ValueError: boom" in captured.err

    def test_usage_error_exit_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(["no-such-command"])
        captured = capsys.readouterr()
        assert code == 2
        assert "No such command" in captured.err
        assert captured.out == ""

    def test_keyboard_interrupt_exit_130(self) -> None:
        def interrupted() -> None:
            """Имитирует Ctrl-C."""
            raise KeyboardInterrupt

        code = run_app(_app_with(run=interrupted), ["run"], GlobalOpts())
        assert code == 130

    def test_verbose_enables_debug_logging(self, capsys: pytest.CaptureFixture[str]) -> None:
        root = logging.getLogger()
        previous = root.level
        try:
            assert main(["--verbose", "--help"]) == 0
            assert root.level == logging.DEBUG
            assert main(["--help"]) == 0
            assert root.level == logging.WARNING
        finally:
            root.setLevel(previous)
        capsys.readouterr()

    def test_json_usage_error_is_object_in_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(["--json", "no-such-command"])
        captured = capsys.readouterr()
        assert code == 2
        assert captured.err == ""
        payload = json.loads(captured.out)
        assert payload["schema_version"] == 1
        assert payload["error"]["code"] == "invalid_value"
