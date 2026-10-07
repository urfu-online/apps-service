"""Тесты слойа вывода ``apps_platform/ui`` (задача T5).

Критерии приёмки T5:
- ``render()`` чистые: не пишут в ``sys.stdout``/``sys.stderr`` (capsys пуст),
  возвращают ``RenderedOut``;
- текст ошибки — только в поле ``stderr``, JSON — только в поле ``stdout``;
- JSON валиден: ``schema_version == 1``, ``error.code``/``error.hint``;
- политика цвета: ``NO_COLOR`` / ``TERM=dumb`` / non-TTY, каналы независимы;
- реестр: регистрация/получение, ``AssertionError`` для незарегистрированного
  типа (с именем типа), регистрация по типу ``PlatformError``;
- golden-текст text-рендера фиксированной ошибки ``command_moved`` (§7.5);
- текст не зависит от ширины терминала (таблиц — в P2).
"""

from __future__ import annotations

import json
import sys
from dataclasses import FrozenInstanceError

import pytest

from apps_platform.core.errors import PlatformError
from apps_platform.ui import console, renderers
from apps_platform.ui.renderers import RenderedOut
from apps_platform.ui.renderers import json as json_renderer
from apps_platform.ui.renderers import text as text_renderer

#: Фиксированное сообщение заглушки §7.5 (мультистрочное — как его соберёт T7).
GOLDEN_MESSAGE = (
    "Команда изменена в platform v2.\n" "Было:     platform deploy api\n" "Стало:    platform service deploy api"
)

GOLDEN_EXPECTED_STDERR = (
    "✘ Команда изменена в platform v2.\n"
    "  Было:     platform deploy api\n"
    "  Стало:    platform service deploy api\n"
    "  Подсказка: platform --help; заглушки будут удалены в v2.1\n"
)


@pytest.fixture
def error() -> PlatformError:
    """Фиксированная ошибка command_moved: hint приходит из реестра §12.4."""
    return PlatformError(code="command_moved", message=GOLDEN_MESSAGE)


@pytest.fixture(autouse=True)
def _restore_registry():
    """Изоляция тестов: реестр — dict в модуле, восстанавливаем после каждого теста."""
    snapshot = dict(renderers.RENDERERS)
    yield
    renderers.RENDERERS.clear()
    renderers.RENDERERS.update(snapshot)


class FakeStream:
    """Канал-заглушка: ``isatty()`` возвращает значение или падает."""

    def __init__(self, tty: bool, *, fail: bool = False) -> None:
        self._tty = tty
        self._fail = fail

    def isatty(self) -> bool:
        if self._fail:
            raise OSError("stream closed")
        return self._tty


class TestPurity:
    """render() — чистые функции: без print, без записи в потоки."""

    def test_text_render_is_pure(self, error: PlatformError, capsys: pytest.CaptureFixture[str]) -> None:
        out = text_renderer.render_error(error)
        assert isinstance(out, RenderedOut)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_json_render_is_pure(self, error: PlatformError, capsys: pytest.CaptureFixture[str]) -> None:
        out = json_renderer.render_error(error)
        assert isinstance(out, RenderedOut)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_registry_dispatch_is_pure(self, error: PlatformError, capsys: pytest.CaptureFixture[str]) -> None:
        renderers.register_defaults(fmt="text")
        out = renderers.get(PlatformError).render(error)
        assert isinstance(out, RenderedOut)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_rendered_out_frozen_and_defaults(self) -> None:
        assert RenderedOut() == RenderedOut(stdout="", stderr="")
        out = RenderedOut(stdout="x")
        with pytest.raises(FrozenInstanceError):
            out.stdout = "y"  # type: ignore[misc]


class TestChannels:
    """Маршрутизация каналов: текст → stderr, JSON → stdout (§12.1, §12.2)."""

    def test_text_error_only_stderr(self, error: PlatformError) -> None:
        out = text_renderer.render_error(error)
        assert out.stdout == ""
        assert out.stderr != ""

    def test_json_error_only_stdout(self, error: PlatformError) -> None:
        out = json_renderer.render_error(error)
        assert out.stderr == ""
        assert out.stdout != ""
        assert out.stdout.endswith("\n")


class TestJsonContract:
    """JSON-ошибка: валидный объект со schema_version в stdout (§12.2)."""

    def test_json_valid_with_schema_version(self, error: PlatformError) -> None:
        payload = json.loads(json_renderer.render_error(error).stdout)
        assert payload["schema_version"] == 1
        assert payload["error"]["code"] == "command_moved"
        assert payload["error"]["hint"] == "platform --help; заглушки будут удалены в v2.1"
        assert payload["error"]["object"] is None
        assert payload["error"]["message"] == GOLDEN_MESSAGE

    def test_json_fields_are_english_machine_keys(self, error: PlatformError) -> None:
        payload = json.loads(json_renderer.render_error(error).stdout)
        assert set(payload) == {"schema_version", "error"}
        assert set(payload["error"]) == {"code", "message", "object", "hint"}

    def test_json_unicode_not_escaped(self) -> None:
        err = PlatformError(code="internal_error", message="Непредвиденная ошибка")
        out = json_renderer.render_error(err)
        assert "Непредвиденная ошибка" in out.stdout

    def test_json_rejects_non_platform_error(self) -> None:
        with pytest.raises(TypeError):
            json_renderer.render_error(object())

    def test_json_never_contains_ansi(self, error: PlatformError) -> None:
        assert "\x1b[" not in json_renderer.render_error(error).stdout


class TestColorPolicy:
    """Политика цвета §12.1: NO_COLOR / TERM=dumb / non-TTY, каналы независимы."""

    def test_no_color_presence_disables_even_on_tty(self) -> None:
        # Присутствие NO_COLOR важнее TTY; значение может быть пустым.
        assert console.colors_enabled(FakeStream(True), env={"NO_COLOR": ""}) is False
        assert console.colors_enabled(FakeStream(True), env={"NO_COLOR": "1"}) is False

    def test_term_dumb_disables(self) -> None:
        assert console.colors_enabled(FakeStream(True), env={"TERM": "dumb"}) is False

    def test_non_tty_disables(self) -> None:
        assert console.colors_enabled(FakeStream(False), env={}) is False

    def test_tty_with_clean_env_enables(self) -> None:
        assert console.colors_enabled(FakeStream(True), env={}) is True

    def test_explicit_no_color_flag_disables(self) -> None:
        assert console.colors_enabled(FakeStream(True), no_color=True, env={}) is False

    def test_broken_isatty_disables(self) -> None:
        assert console.colors_enabled(FakeStream(True, fail=True), env={}) is False

    def test_no_color_read_from_live_environ(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NO_COLOR", "1")
        policy = console.ColorPolicy(stdout=FakeStream(True), stderr=FakeStream(True))
        assert policy.stdout_colors() is False
        assert policy.stderr_colors() is False

    def test_term_dumb_read_from_live_environ(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setenv("TERM", "dumb")
        policy = console.ColorPolicy(stdout=FakeStream(True), stderr=FakeStream(True))
        assert policy.stdout_colors() is False
        assert policy.stderr_colors() is False

    def test_channels_decided_independently(self) -> None:
        policy = console.ColorPolicy(env={}, stdout=FakeStream(True), stderr=FakeStream(False))
        assert policy.stdout_colors() is True
        assert policy.stderr_colors() is False
        mirrored = console.ColorPolicy(env={}, stdout=FakeStream(False), stderr=FakeStream(True))
        assert mirrored.stdout_colors() is False
        assert mirrored.stderr_colors() is True

    def test_policy_defaults_to_live_sys_streams(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setattr(sys, "stdout", FakeStream(True))
        monkeypatch.setattr(sys, "stderr", FakeStream(False))
        policy = console.ColorPolicy(env={})
        assert policy.stdout_colors() is True
        assert policy.stderr_colors() is False

    def test_build_console_respects_policy(self) -> None:
        off = console.build_console("stdout", policy=console.ColorPolicy(no_color=True, env={}))
        assert off.no_color is True
        on = console.build_console(
            "stdout",
            policy=console.ColorPolicy(env={}, stdout=FakeStream(True)),
        )
        assert on.no_color is False

    def test_build_console_rejects_unknown_channel(self) -> None:
        with pytest.raises(ValueError):
            console.build_console("stdin")  # type: ignore[arg-type]


class TestRegistry:
    """Реестр: register/get, AssertionError для незарегистрированного типа."""

    def test_register_and_get_by_type(self, error: PlatformError) -> None:
        def fake_renderer(result: object) -> RenderedOut:
            return RenderedOut(stderr=f"handled {type(result).__name__}")

        class CustomResult:
            pass

        renderers.register(CustomResult, fake_renderer)
        renderer = renderers.get(CustomResult)
        assert isinstance(renderer, renderers.Renderer)
        assert renderer.render(CustomResult()) == RenderedOut(stderr="handled CustomResult")

    def test_register_accepts_object_with_render_method(self, error: PlatformError) -> None:
        class ObjRenderer:
            def render(self, result: object) -> RenderedOut:
                return RenderedOut(stdout="via-method")

        renderers.register(PlatformError, ObjRenderer())
        assert renderers.get(PlatformError).render(error) == RenderedOut(stdout="via-method")

    def test_get_unregistered_type_raises_assertion_with_name(self) -> None:
        class UnregisteredResult:
            pass

        with pytest.raises(AssertionError) as excinfo:
            renderers.get(UnregisteredResult)
        assert "UnregisteredResult" in str(excinfo.value)

    def test_register_by_platform_error_type(self, error: PlatformError) -> None:
        renderers.register(PlatformError, lambda result: RenderedOut(stderr="by-type"))
        assert renderers.get(PlatformError).render(error) == RenderedOut(stderr="by-type")

    def test_register_rejects_non_type_key(self) -> None:
        with pytest.raises(TypeError):
            renderers.register("PlatformError", lambda result: RenderedOut())  # type: ignore[arg-type]

    def test_register_defaults_text_goes_to_stderr(self, error: PlatformError) -> None:
        renderers.register_defaults(fmt="text")
        out = renderers.get(PlatformError).render(error)
        assert out.stdout == ""
        assert out.stderr == GOLDEN_EXPECTED_STDERR

    def test_register_defaults_json_goes_to_stdout(self, error: PlatformError) -> None:
        renderers.register_defaults(fmt="json")
        out = renderers.get(PlatformError).render(error)
        assert out.stderr == ""
        assert json.loads(out.stdout)["schema_version"] == 1

    def test_register_defaults_default_format_is_text(self, error: PlatformError) -> None:
        renderers.register_defaults()
        out = renderers.get(PlatformError).render(error)
        assert out.stderr != "" and out.stdout == ""

    def test_register_defaults_rejects_unknown_format(self) -> None:
        with pytest.raises(ValueError):
            renderers.register_defaults(fmt="ndjson")  # type: ignore[arg-type]

    def test_register_defaults_binds_color_policy(self, error: PlatformError) -> None:
        policy = console.ColorPolicy(env={}, stderr=FakeStream(True))
        renderers.register_defaults(fmt="text", color_policy=policy)
        out = renderers.get(PlatformError).render(error)
        assert "\x1b[31m" in out.stderr

    def test_register_defaults_text_color_off_for_non_tty(self, error: PlatformError) -> None:
        policy = console.ColorPolicy(env={}, stderr=FakeStream(False))
        renderers.register_defaults(fmt="text", color_policy=policy)
        out = renderers.get(PlatformError).render(error)
        assert "\x1b[" not in out.stderr


class TestTextRendering:
    """Текстовый рендерер: 4 вопроса §12.3, цвета опциональны."""

    def test_text_rejects_non_platform_error(self) -> None:
        with pytest.raises(TypeError):
            text_renderer.render_error(object())

    def test_object_line_rendered(self) -> None:
        err = PlatformError(code="service_not_found", message="Сервис не найден.", object="api")
        out = text_renderer.render_error(err)
        assert out.stderr == ("✘ Сервис не найден.\n" "  Объект: api\n" "  Подсказка: platform service list --json\n")

    def test_no_hint_no_object_single_line(self) -> None:
        err = PlatformError(code="cancelled", message="Операция прервана по Ctrl-C; ничего не изменено.")
        out = text_renderer.render_error(err)
        assert out.stderr == "✘ Операция прервана по Ctrl-C; ничего не изменено.\n"

    def test_color_disabled_by_default(self, error: PlatformError) -> None:
        assert "\x1b[" not in text_renderer.render_error(error).stderr

    def test_color_enabled_via_policy(self, error: PlatformError) -> None:
        policy = console.ColorPolicy(env={}, stderr=FakeStream(True))
        out = text_renderer.render_error(error, policy)
        assert "\x1b[31m" in out.stderr
        assert out.stderr.endswith("\x1b[0m\n") or "\x1b[0m\n  Подсказка" in out.stderr

    def test_color_disabled_by_no_color_env(self, error: PlatformError, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NO_COLOR", "")
        policy = console.ColorPolicy(stderr=FakeStream(True))
        assert "\x1b[" not in text_renderer.render_error(error, policy).stderr

    def test_output_independent_of_width(self, error: PlatformError, monkeypatch: pytest.MonkeyPatch) -> None:
        outputs = []
        for columns in ("60", "80", "120"):
            monkeypatch.setenv("COLUMNS", columns)
            outputs.append(text_renderer.render_error(error).stderr)
        assert outputs[0] == outputs[1] == outputs[2]


class TestGolden:
    """Golden-снапшот текстового рендера (в снапшоте внутри теста, без файлов)."""

    def test_command_moved_golden(self, error: PlatformError) -> None:
        out = text_renderer.render_error(error)
        assert out.stderr == GOLDEN_EXPECTED_STDERR
        assert out.stdout == ""

    def test_command_moved_matches_section_7_5(self, error: PlatformError) -> None:
        # Образец §7.5: маркер, «Было/Стало» через message, подсказка в конце.
        stderr = text_renderer.render_error(error).stderr
        assert stderr.startswith("✘ Команда изменена в platform v2.\n")
        assert "  Было:     platform deploy api\n" in stderr
        assert "  Стало:    platform service deploy api\n" in stderr
        assert stderr.endswith("  Подсказка: platform --help; заглушки будут удалены в v2.1\n")
