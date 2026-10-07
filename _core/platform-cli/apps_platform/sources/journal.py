"""Скелет адаптера порта ``Journal`` (T6; журнал операций).

Наполняется в P4 (§13.5: журнал операций); формат записи и хранилище в P1
не определяются, тела методов — заглушки.
"""

from __future__ import annotations


class JournalAdapter:
    """Адаптер порта ``Journal`` (наполняется в P4)."""

    def record(self, event: str) -> object:
        """Запись события в журнал — заготовка; наполняется в P4."""
        raise NotImplementedError("Journal.record() наполняется в P4")
