"""Тесты ``apps_platform/core/errors.py`` (задача T1).

Покрывают критерии приёмки:
- полнота закрытого реестра против таблицы §12.4 (полный список кодов в тесте);
- exit-маппинг ``code → exit`` для каждого кода (включая ``command_moved`` → 2);
- ``wrap_unexpected`` → 1 с ``cause``; ``cancelled`` → 130;
- неизвестный ``code`` → AssertionError/KeyError; ``exit_code`` не задаётся вызывающим;
- ``to_json`` валиден и содержит ``schema_version``;
- frozen-семантика полей + разрешение служебных атрибутов исключения
  (``__traceback__`` и т.п.): ``PlatformError`` выходит наружу через
  contextlib-обёртку Typer как ``PlatformError``, а не ``FrozenInstanceError``.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from dataclasses import FrozenInstanceError

import pytest
import typer
from typer.testing import CliRunner

from apps_platform.core.errors import (
    ERROR_REGISTRY,
    SCHEMA_VERSION,
    PlatformError,
    cancelled,
    wrap_unexpected,
)

# Полный список кодов §12.4 спеки (включая command_moved из §7.5) → exit.
# Сверяется 1-в-1 с ERROR_REGISTRY: ни лишнего, ни отсутствующего кода.
SPEC_CODES: dict[str, int] = {
    "arg_missing": 2,
    "service_not_found": 2,
    "service_exists": 2,
    "name_invalid": 2,
    "port_conflict": 2,
    "section_unknown": 2,
    "no_tty": 2,
    "invalid_value": 2,
    "command_moved": 2,
    "config_not_found": 3,
    "docker_unavailable": 3,
    "master_unavailable": 3,
    "master_incompatible": 3,
    "environment_mismatch": 3,
    "lock_busy": 3,
    "compose_failed": 1,
    "step_failed": 1,
    "postcheck_failed": 1,
    "snapshot_not_found": 2,
    "restore_conflict": 2,
    "cancelled": 130,
    "internal_error": 1,
}


class TestRegistryCompleteness:
    """(а) реестр кодов — ровно таблица §12.4, каждый код один раз."""

    def test_registry_keys_match_spec_1_to_1(self) -> None:
        assert set(ERROR_REGISTRY) == set(SPEC_CODES)

    def test_registry_has_no_duplicates(self) -> None:
        assert len(ERROR_REGISTRY) == len(SPEC_CODES)

    def test_registry_is_immutable(self) -> None:
        with pytest.raises(TypeError):
            ERROR_REGISTRY["new_code"] = None  # type: ignore[index]

    def test_every_code_has_exit_and_hint_entry(self) -> None:
        for code in SPEC_CODES:
            spec = ERROR_REGISTRY[code]
            assert spec.exit_code > 0
            # у всех кодов есть hint-шаблон, кроме cancelled («—» в §12.4)
            if code != "cancelled":
                assert isinstance(spec.hint, str) and spec.hint

    def test_command_moved_hint_matches_section_7_5(self) -> None:
        assert ERROR_REGISTRY["command_moved"].hint == "platform --help; заглушки будут удалены в v2.1"


class TestExitMapping:
    """(б) exit-код каждого code совпадает со спекой §12.4."""

    @pytest.mark.parametrize(("code", "exit_code"), sorted(SPEC_CODES.items()))
    def test_registry_exit_code(self, code: str, exit_code: int) -> None:
        assert ERROR_REGISTRY[code].exit_code == exit_code

    @pytest.mark.parametrize(("code", "exit_code"), sorted(SPEC_CODES.items()))
    def test_platform_error_exit_code_from_registry(self, code: str, exit_code: int) -> None:
        err = PlatformError(code=code, message="m")
        assert err.exit_code == exit_code

    def test_command_moved_is_exit_2(self) -> None:
        assert PlatformError(code="command_moved", message="m").exit_code == 2

    def test_exit_code_not_settable_by_caller(self) -> None:
        with pytest.raises(TypeError):
            PlatformError(code="internal_error", message="m", exit_code=2)  # type: ignore[call-arg]

    def test_exit_code_is_read_only(self) -> None:
        err = PlatformError(code="internal_error", message="m")
        with pytest.raises(AttributeError):
            err.exit_code = 2  # type: ignore[misc]

    def test_unknown_code_rejected(self) -> None:
        with pytest.raises((AssertionError, KeyError)):
            PlatformError(code="no_such_code", message="m")


class TestFactories:
    """(в) wrap_unexpected → 1 с cause; (г) cancelled → 130."""

    def test_wrap_unexpected(self) -> None:
        exc = ValueError("boom")
        err = wrap_unexpected(exc)
        assert err.code == "internal_error"
        assert err.exit_code == 1
        assert err.cause is exc
        assert "ValueError" in err.message

    def test_cancelled(self) -> None:
        err = cancelled()
        assert err.code == "cancelled"
        assert err.exit_code == 130

    def test_default_hint_from_registry(self) -> None:
        err = PlatformError(code="config_not_found", message="m")
        assert err.hint == ERROR_REGISTRY["config_not_found"].hint

    def test_hint_override_allowed(self) -> None:
        err = PlatformError(code="port_conflict", message="m", hint="порт 8080")
        assert err.hint == "порт 8080"

    def test_error_is_frozen(self) -> None:
        err = PlatformError(code="internal_error", message="m")
        with pytest.raises(AttributeError):
            err.message = "other"  # type: ignore[misc]


class TestToJson:
    """(д) to_json валиден, содержит schema_version."""

    def test_to_json_is_valid_object(self) -> None:
        err = PlatformError(code="service_not_found", message="нет сервиса", object="api")
        payload = err.to_json()
        assert payload["schema_version"] == SCHEMA_VERSION == 1
        assert set(payload["error"]) == {"code", "message", "object", "hint"}
        assert payload["error"]["code"] == "service_not_found"
        assert payload["error"]["object"] == "api"

    def test_to_json_roundtrip(self) -> None:
        err = PlatformError(code="internal_error", message="сбой", cause=ValueError("x"))
        parsed = json.loads(json.dumps(err.to_json(), ensure_ascii=False))
        assert parsed["schema_version"] == 1
        assert parsed["error"]["code"] == "internal_error"
        assert parsed["error"]["message"] == "сбой"
        assert "cause" not in parsed["error"]

    def test_to_json_null_fields(self) -> None:
        err = PlatformError(code="cancelled", message="прервано")
        parsed = json.loads(json.dumps(err.to_json(), ensure_ascii=False))
        assert parsed["error"]["object"] is None
        assert parsed["error"]["hint"] is None


class TestExceptionInternalAttrs:
    """(е) frozen для полей; служебные атрибуты исключения разрешены.

    Регрессия T7→T9: ``contextlib._GeneratorContextManager.__exit__`` на выходе
    из ``@contextmanager``-обёртки команд Typer выполняет
    ``exc.__traceback__ = traceback`` (bpo-27122). Замороженный
    ``__setattr__`` датакласса отвечал ``FrozenInstanceError`` — любой
    ``PlatformError`` наружу утекал бы как ``FrozenInstanceError`` и
    превращался в ``internal_error`` (exit 1) вместо кода из реестра.
    """

    @pytest.mark.parametrize(
        ("attr", "value"),
        [
            ("__traceback__", None),
            ("__context__", None),
            ("__cause__", None),
            ("__notes__", None),
            # у __suppress_context__ дескриптор BaseException валидирует bool
            ("__suppress_context__", True),
        ],
    )
    def test_service_exception_attributes_settable(self, attr: str, value: object) -> None:
        err = PlatformError(code="command_moved", message="m")
        setattr(err, attr, value)
        assert getattr(err, attr) is value

    def test_traceback_assignment_does_not_raise(self) -> None:
        err = PlatformError(code="internal_error", message="m")
        err.__traceback__ = None  # ровно то, что делает contextlib.__exit__
        assert err.__traceback__ is None

    def test_fields_still_frozen(self) -> None:
        err = PlatformError(code="command_moved", message="m")
        with pytest.raises(FrozenInstanceError):
            err.code = "x"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            err.message = "x"  # type: ignore[misc]

    def test_exit_code_still_read_only(self) -> None:
        err = PlatformError(code="command_moved", message="m")
        with pytest.raises(AttributeError):
            err.exit_code = 2  # type: ignore[misc]
        assert err.exit_code == 2

    def test_unknown_non_dunder_attribute_rejected(self) -> None:
        err = PlatformError(code="command_moved", message="m")
        with pytest.raises(FrozenInstanceError):
            err.other = "x"  # type: ignore[attr-defined]

    def test_contextmanager_rethrow_keeps_error_usable(self) -> None:
        @contextlib.contextmanager
        def augment_usage_errors() -> Iterator[None]:
            """Имитация ``augment_usage_errors`` из Typer (``@contextmanager``)."""

            yield

        with pytest.raises(PlatformError) as excinfo, augment_usage_errors():
            raise PlatformError(code="command_moved", message="m")

        err = excinfo.value
        assert type(err) is PlatformError
        assert err.__traceback__ is not None
        assert err.exit_code == 2
        assert err.to_json()["error"]["code"] == "command_moved"

    def test_platform_error_exits_typer_as_platform_error(self) -> None:
        """Интеграция: CliRunner → typer → contextlib снаружи PlatformError."""
        app = typer.Typer(add_completion=False)

        @app.command()
        def boom() -> None:
            """Команда, бросающая PlatformError."""
            raise PlatformError(code="command_moved", message="m")

        @app.command()
        def hello() -> None:
            """Вторая команда — чтобы Typer собрал группу, а не single-command app."""

        with pytest.raises(PlatformError) as excinfo:
            CliRunner().invoke(app, ["boom"], catch_exceptions=False)

        err = excinfo.value
        assert type(err) is PlatformError
        assert err.exit_code == 2
        assert err.__traceback__ is not None
        assert err.to_json()["error"]["code"] == "command_moved"
