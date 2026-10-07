"""Политика вывода: цвет по каналам stdout/stderr — §12.1 спеки.

Цвета включаются, только если выполняются **все** условия (любое отключает):

1. явный флаг ``no_color=True`` (``--no-color``, §7.4);
2. в env **присутствует** ``NO_COLOR`` — любое значение, включая пустое
   (NO_COLOR.org), и это важнее TTY;
3. ``TERM`` не равен ``dumb``;
4. сам канал — TTY: ``stream.isatty()`` истинно (перенаправление в пайп/file
   гасит цвета).

Каналы независимы: политика для stdout и stderr принимается отдельно
(``ColorPolicy.stdout_colors()`` / ``stderr_colors()``). Env читается в момент
вызова (``os.environ``), а не при иморте, — тесты и composition root меняют
окружение без перезагрузки модуля.

Rich-обёртка ``build_console`` опциональна: рендереры возвращают строки и
работают без Rich; печатает в потоки только ``cli.py``.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from rich.console import Console

__all__ = ["ColorPolicy", "build_console", "colors_enabled"]


@runtime_checkable
class _SupportsIsatty(Protocol):
    """Минимальный канал: достаточно метода ``isatty()`` (тесты подменяют его)."""

    def isatty(self) -> bool: ...


def colors_enabled(stream: _SupportsIsatty, *, no_color: bool = False, env: Mapping[str, str] | None = None) -> bool:
    """Цвета включены для одного канала? Правила — в докстринге модуля (§12.1).

    ``env=None`` → ``os.environ`` в момент вызова; иначе — переданный mapping
    (тесты изолируют окружение явно).
    """
    if no_color:
        return False
    environ = os.environ if env is None else env
    if "NO_COLOR" in environ:
        return False
    if environ.get("TERM") == "dumb":
        return False
    isatty = getattr(stream, "isatty", None)
    if isatty is None:
        return False
    try:
        return bool(isatty())
    except (OSError, ValueError):
        # Недоступный/закрытый терминал — считаем перенаправлением.
        return False


@dataclass(frozen=True)
class ColorPolicy:
    """Цветовая политика каналов stdout и stderr; каналы независимы (§12.1).

    Поля ``stdout``/``stderr`` — каналы (по умолчанию ``sys.stdout``/``sys.stderr``
    в момент вызова); ``env`` — mapping окружения (``None`` → ``os.environ``).
    """

    no_color: bool = False
    env: Mapping[str, str] | None = None
    stdout: _SupportsIsatty | None = None
    stderr: _SupportsIsatty | None = None

    def stdout_colors(self) -> bool:
        """Цвета для канала stdout при этой политике."""
        stream = sys.stdout if self.stdout is None else self.stdout
        return colors_enabled(stream, no_color=self.no_color, env=self.env)

    def stderr_colors(self) -> bool:
        """Цвета для канала stderr при этой политике."""
        stream = sys.stderr if self.stderr is None else self.stderr
        return colors_enabled(stream, no_color=self.no_color, env=self.env)


def build_console(channel: Literal["stdout", "stderr"] = "stdout", *, policy: ColorPolicy | None = None) -> Console:
    """Rich-Console для канала с учётом политики цвета (опциональный помощник).

    Рендереры Rich не используют: они возвращают строки в ``RenderedOut``.
    """
    active = policy if policy is not None else ColorPolicy()
    if channel == "stdout":
        stream = sys.stdout if active.stdout is None else active.stdout
        colors = active.stdout_colors()
    elif channel == "stderr":
        stream = sys.stderr if active.stderr is None else active.stderr
        colors = active.stderr_colors()
    else:
        raise ValueError(f"неизвестный канал: {channel!r} (допустимо: 'stdout', 'stderr')")
    return Console(file=stream, no_color=not colors)
