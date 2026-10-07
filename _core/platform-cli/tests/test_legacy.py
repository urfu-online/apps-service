"""Тесты заглушек старых команд §7.5 (задача T7, ``commands/legacy.py``).

Покрывают критерии приёмки:

- параметризация по всем 9 заглушкам: ``PlatformError``, ``code="command_moved"``,
  ``exit_code == 2``, «Было:»/«Стало:» и правильный новый вызов (§7.2);
- ``build_moved_message`` — golden-строка §7.5 (без строки «Подсказка:» —
  hint добавляет text-рендерер из реестра, ровно одна подсказка в stderr);
- ``CliRunner`` на временном приложении с ``register(app)``: заглушки работают,
  в ``--help`` не видны, вывода в stdout нет;
- boundary ``main``: итоговый stderr содержит ровно одну строку «Подсказка:»;
- v1-команды (``commands/services.py`` и др.) и их тесты не затрагиваются.
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest
import typer
from typer.core import TyperGroup
from typer.testing import CliRunner

from apps_platform.cli import main
from apps_platform.commands.legacy import (
    LEGACY_MOVES,
    build_moved_message,
    register,
)
from apps_platform.core.errors import PlatformError

# Ровно 9 заглушек §7.5 (дубль ``status`` — тоже заглушка до P2).
EXPECTED_STUBS: set[str] = {"deploy", "stop", "restart", "logs", "backup", "new", "list", "reload", "status"}

# (старое имя, хвост вызова, ожидаемый новый вызов после «platform »).
MOVED_CASES: list[tuple[str, list[str], str]] = [
    ("deploy", ["api"], "service deploy api"),
    ("stop", ["api"], "service stop api"),
    ("restart", ["api"], "service restart api"),
    ("logs", ["--tail", "100"], "service logs --tail 100"),
    ("backup", ["api"], "backup create api"),
    ("backup", ["list"], "backup list"),
    ("backup", [], "backup"),
    ("new", ["billing"], "service create billing"),
    ("list", [], "service list"),
    ("reload", [], "proxy reload"),
    ("status", ["api"], "status api"),
]


def make_app() -> typer.Typer:
    """Временное приложение: заглушки ``register()`` + одна видимая команда."""
    app = typer.Typer(add_completion=False)
    register(app)

    @app.command()
    def hello() -> None:
        """Видимая команда — для проверки ``--help``."""

    return app


class TestStubHandlers:
    """Каждая заглушка бросает PlatformError(command_moved, exit 2) с §7.5-текстом."""

    @pytest.mark.parametrize(
        ("old_name", "rest", "new_call"),
        MOVED_CASES,
        ids=[f"{old}-{'-'.join(rest) or 'bare'}" for old, rest, _ in MOVED_CASES],
    )
    def test_raises_command_moved_with_message_section_7_5(self, old_name: str, rest: list[str], new_call: str) -> None:
        app = make_app()
        with pytest.raises(PlatformError) as excinfo:
            CliRunner().invoke(app, [old_name, *rest], catch_exceptions=False)

        err = excinfo.value
        old_call = " ".join([old_name, *rest])
        assert err.code == "command_moved"
        assert err.exit_code == 2
        assert err.message.startswith("Команда изменена в platform v2.")
        assert f"Было: platform {old_call}" in err.message
        assert f"Стало: platform {new_call}" in err.message
        # Подсказка — в hint из реестра §12.4, НЕ в message (иначе двойной hint, T8→T9)
        assert "Подсказка:" not in err.message
        assert err.hint == "platform --help; заглушки будут удалены в v2.1"
        assert err.object == old_call

    def test_mapping_covers_exactly_the_nine_stubs(self) -> None:
        assert set(LEGACY_MOVES) == EXPECTED_STUBS
        assert len(LEGACY_MOVES) == 9

    def test_unknown_options_are_accepted_and_ignored(self) -> None:
        app = make_app()
        with pytest.raises(PlatformError) as excinfo:
            CliRunner().invoke(app, ["deploy", "api", "--build", "--quiet"], catch_exceptions=False)

        err = excinfo.value
        assert err.code == "command_moved"
        assert "Было: platform deploy api --build --quiet" in err.message
        assert "Стало: platform service deploy api --build --quiet" in err.message

    def test_stub_prints_nothing_to_output(self) -> None:
        app = make_app()
        result = CliRunner().invoke(app, ["deploy", "api"], catch_exceptions=True)
        assert isinstance(result.exception, PlatformError)
        assert result.output == ""


class TestBuildMovedMessage:
    """Чистая функция сборки сообщения — golden-строка §7.5 / кейс C7.

    В message намеренно **нет** строки «Подсказка:» (находка T8): hint
    ``command_moved`` добавляет text-рендерер boundary из реестра §12.4.
    """

    def test_golden_section_7_5(self) -> None:
        assert build_moved_message(["deploy", "api"], "service deploy api") == (
            "Команда изменена в platform v2.\n" "Было: platform deploy api\n" "Стало: platform service deploy api"
        )

    def test_no_args_call(self) -> None:
        assert build_moved_message(["reload"], "proxy reload") == (
            "Команда изменена в platform v2.\n" "Было: platform reload\n" "Стало: platform proxy reload"
        )

    def test_three_lines_without_hint(self) -> None:
        message = build_moved_message(["list"], "service list")
        assert len(message.splitlines()) == 3
        assert message.splitlines()[0] == "Команда изменена в platform v2."
        assert "Подсказка:" not in message


class TestRenderedOutputSingleHint:
    """Итоговый вывод boundary: ровно одна строка «Подсказка:» в stderr (T9)."""

    def test_rendered_stderr_has_exactly_one_hint_line(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(["deploy", "api"])
        captured = capsys.readouterr()
        assert code == 2
        assert captured.out == ""
        hint_lines = [line for line in captured.err.splitlines() if "Подсказка:" in line]
        assert len(hint_lines) == 1
        assert hint_lines[0].strip() == "Подсказка: platform --help; заглушки будут удалены в v2.1"

    def test_rendered_json_error_has_single_hint_field(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(["deploy", "api", "--json"])
        captured = capsys.readouterr()
        assert code == 2
        assert captured.err == ""
        payload = json.loads(captured.out)
        assert payload["error"]["hint"] == "platform --help; заглушки будут удалены в v2.1"
        assert "Подсказка:" not in payload["error"]["message"]


class TestRegister:
    """``register(app)``: все 9 заглушек на приложении и скрыты в help."""

    def test_all_stubs_registered_hidden(self) -> None:
        group = typer.main.get_command(make_app())
        assert isinstance(group, TyperGroup)
        assert set(group.commands) >= EXPECTED_STUBS
        for name in EXPECTED_STUBS:
            assert group.commands[name].hidden is True
        assert group.commands["hello"].hidden is False

    def test_help_does_not_list_stubs(self) -> None:
        result = CliRunner().invoke(make_app(), ["--help"], catch_exceptions=False)
        assert result.exit_code == 0

        # Первая «читаемая» слово каждой строки help-вывода: имя команды либо
        # слово описания/заголовка (рамки rich пропускаются). Заглушки не должны
        # встречаться как команды; видимая — должна.
        first_tokens = {
            next(token for token in line.split() if any(ch.isalnum() for ch in token))
            for line in result.output.splitlines()
            if any(ch.isalnum() for ch in line)
        }
        assert EXPECTED_STUBS & first_tokens == set()
        assert "hello" in first_tokens

    def test_two_apps_independent(self) -> None:
        app_a, app_b = make_app(), make_app()
        for app in (app_a, app_b):
            with pytest.raises(PlatformError) as excinfo:
                CliRunner().invoke(app, ["new", "svc"], catch_exceptions=False)
            assert excinfo.value.exit_code == 2


class TestStubErrorPropagation:
    """Заглушки бросают базовый ``PlatformError``, переживающий contextmanager.

    Раньше для этого требовался подкласс ``_CommandMovedError``; с фиксом
    frozen-``__setattr__`` в ``core/errors.py`` служебные атрибуты исключения
    (``exc.__traceback__ = traceback`` из contextlib-обёртки Typer)
    записываются на базовом классе, и обход больше не нужен.
    """

    def test_stub_error_is_base_platform_error(self) -> None:
        err = PlatformError(code="command_moved", message="m")
        assert type(err) is PlatformError
        # ровно то, что делает contextlib.__exit__ при выходе из
        # typer augment_usage_errors: exc.__traceback__ = traceback
        err.__traceback__ = None
        assert err.__traceback__ is None

    def test_fields_still_frozen(self) -> None:
        err = PlatformError(code="command_moved", message="m")
        with pytest.raises(FrozenInstanceError):
            err.message = "other"  # type: ignore[misc]
        assert err.exit_code == 2

    def test_survives_contextmanager_propagation(self) -> None:
        app = make_app()
        # CliRunner.invoke → cli.main → augment_usage_errors (обе — @contextmanager)
        with pytest.raises(PlatformError) as excinfo:
            CliRunner().invoke(app, ["deploy", "api"], catch_exceptions=False)
        assert type(excinfo.value) is PlatformError
        assert excinfo.value.code == "command_moved"
