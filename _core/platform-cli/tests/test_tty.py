"""Тесты T10: TTY/non-TTY контур ``platform2`` через pty (§12.1, §18.1-P1, §18.2 п.3).

Схема — **два pty** (:func:`tests.fixtures.support.run_platform2_tty`): stdout и
stderr подключены к разным slave-парам, поэтому чтение master'ов разделяет
слоты каналов (в stdout-слот не попадает то, что написано в stderr), а
``isatty()`` истинно для обоих потоков — TTY-статус проверяется реально, без
осциллогов. ``stdin`` — ``/dev/null``: P1-команды ввод не читают, политика
цвета §12.1 зависит только от stdout/stderr. Переводы строк pty (``\\r\\n``)
нормализуются в ``\\n``.

Покрытие критерия (г) §18.1-P1: текст ошибки идёт в stderr-слот при TTY;
цвет включается на TTY (``TERM=xterm``) и каждый переключатель — ``NO_COLOR``,
``TERM=dumb``, ``--no-color`` — по отдельности гасит ANSI; non-TTY без
``NO_COLOR`` (только ``TERM=xterm-256color``) — тоже без ANSI.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from tests.fixtures.support import make_env, run_platform2, run_platform2_tty, strip_ansi

#: Окружение TTY-прогона «цвет разрешён»: NO_COLOR снят, TERM задан.
_COLOR_OK: dict[str, str | None] = {"NO_COLOR": None, "TERM": "xterm"}


def tty_cli(
    tmp_path: Path,
    *args: str,
    overrides: Mapping[str, str | None] | None = None,
) -> tuple[int, str, str]:
    """``platform2 <args>`` c TTY на stdout и stderr → ``(exit, stdout, stderr)``."""
    return run_platform2_tty(args, cwd=tmp_path, env=make_env(tmp_path, overrides))


class TestTTYChannels:
    """Разделение каналов при реальном TTY: текст ошибки — в stderr-слот."""

    def test_stub_error_goes_to_stderr_slot_only(self, tmp_path: Path) -> None:
        code, stdout, stderr = tty_cli(tmp_path, "deploy", "api", overrides=_COLOR_OK)
        assert code == 2
        assert stdout == ""  # в stdout-слоте ошибки нет
        assert "Команда изменена в platform v2." in stderr
        assert stderr.count("Подсказка:") == 1
        assert "Traceback" not in stderr

    def test_help_goes_to_stdout_slot_only(self, tmp_path: Path) -> None:
        code, stdout, stderr = tty_cli(tmp_path, "--help", overrides=_COLOR_OK)
        assert code == 0
        assert stderr == ""
        # На TTY rich добавляет ANSI-стили — текст сверяется без них.
        assert "Usage: platform2 [OPTIONS] COMMAND [ARGS]..." in strip_ansi(stdout)


class TestTTYColors:
    """Цвет на TTY и каждый переключатель отключения — по отдельности (§12.1)."""

    def test_colors_enabled_on_tty_with_term_xterm(self, tmp_path: Path) -> None:
        code, stdout, stderr = tty_cli(tmp_path, "deploy", "api", overrides=_COLOR_OK)
        assert code == 2
        assert stdout == ""
        assert "\x1b[31m" in stderr  # красный маркер ✘ (ui/renderers/text.py)

    def test_no_color_env_disables_colors_on_tty(self, tmp_path: Path) -> None:
        code, _, stderr = tty_cli(tmp_path, "deploy", "api", overrides={"NO_COLOR": "1", "TERM": "xterm"})
        assert code == 2
        assert "\x1b" not in stderr

    def test_term_dumb_disables_colors_on_tty(self, tmp_path: Path) -> None:
        code, _, stderr = tty_cli(tmp_path, "deploy", "api", overrides={"NO_COLOR": None, "TERM": "dumb"})
        assert code == 2
        assert "\x1b" not in stderr

    def test_no_color_flag_disables_colors_on_tty(self, tmp_path: Path) -> None:
        code, stdout, stderr = tty_cli(tmp_path, "deploy", "api", "--no-color", overrides=_COLOR_OK)
        assert code == 2
        assert stdout == ""
        assert "\x1b" not in stderr

    def test_help_colored_on_tty(self, tmp_path: Path) -> None:
        """Контроль «цвет вообще возможен»: help на TTY содержит ANSI в stdout."""
        code, stdout, _ = tty_cli(tmp_path, "--help", overrides=_COLOR_OK)
        assert code == 0
        assert "\x1b" in stdout


class TestNonTTY:
    """Перенаправление (pipe) само по себе гасит цвет — даже при ``TERM`` (§12.1)."""

    def test_no_ansi_without_no_color_when_term_is_xterm_256color(self, tmp_path: Path) -> None:
        """Только non-TTY (``NO_COLOR`` снят, ``TERM`` задан) → ни одного ``\\x1b``."""
        env = make_env(tmp_path, {"NO_COLOR": None, "TERM": "xterm-256color"})
        stub = run_platform2(("deploy", "api"), cwd=tmp_path, env=env)
        help_result = run_platform2(("--help",), cwd=tmp_path, env=env)
        assert stub.returncode == 2
        assert help_result.returncode == 0
        for result in (stub, help_result):
            assert "\x1b" not in result.stdout
            assert "\x1b" not in result.stderr

    def test_no_ansi_in_default_non_tty_run(self, tmp_path: Path) -> None:
        """Дефолт прогона (``NO_COLOR=1``, без pty) — без ANSI в обоих слотах."""
        result = run_platform2(("deploy", "api"), cwd=tmp_path, env=make_env(tmp_path))
        assert result.returncode == 2
        assert "\x1b" not in result.stdout
        assert "\x1b" not in result.stderr
