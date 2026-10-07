"""Обёртка над ``legacy_cli.platform_lock()`` + заготовка порта ``LockManager`` (T6).

``hold()`` — рабочая в P1 обёртка context manager: конвертирует ``typer.Exit``
v1 (занятость/таймаут файлового lock'а) в ``PlatformError(lock_busy)`` —
exit 3 по реестру §12.4. Сама логика ``fcntl.flock`` остаётся в v1 до P3;
scoped locks (метод ``acquire`` порта) наполняются в P3 (§13.4).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager

from apps_platform import legacy_cli
from apps_platform.core.errors import PlatformError

#: ``typer.Exit`` v1 доступен только через ``legacy_cli`` (импорт Typer в ``sources/`` запрещён).
_Exit = legacy_cli.typer.Exit


class LocksManager:
    """Адаптер порта ``LockManager`` (методы порта наполняются в P3: scoped locks, §13.4)."""

    def acquire(self, key: str) -> object:
        """Lock по ключу — заготовка; наполняется в P3."""
        raise NotImplementedError("LockManager.acquire() наполняется в P3")

    @contextmanager
    def hold(self, *, blocking: bool = False, timeout: float = 0.0) -> Iterator[None]:
        """Глобальный lock одной операции CLI поверх ``legacy_cli.platform_lock``.

        Конвертирует ``typer.Exit`` v1 только на этапе захвата: исключения
        тела ``with`` проходят насквозь и не превращаются в ``lock_busy``.

        Raises:
            PlatformError: ``lock_busy`` — lock занят другой командой CLI.
        """
        with ExitStack() as stack:
            try:
                stack.enter_context(legacy_cli.platform_lock(blocking=blocking, timeout=timeout))
            except _Exit as exc:
                raise PlatformError(
                    code="lock_busy",
                    message="Другая команда platform уже выполняется (lock занят).",
                    cause=exc,
                ) from exc
            yield
