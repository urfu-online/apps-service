"""Скелет адаптера порта ``CacheStore`` (T6; кэш снапшотов completion).

Наполняется в P5 (§14: completion snapshots); хранилище и формат снапшотов
в P1 не выбираются, тела методов — заглушки.
"""

from __future__ import annotations


class CacheAdapter:
    """Адаптер порта ``CacheStore`` (наполняется в P5)."""

    def get(self, key: str) -> object:
        """Чтение значения из кэша — заготовка; наполняется в P5."""
        raise NotImplementedError("CacheStore.get() наполняется в P5")
