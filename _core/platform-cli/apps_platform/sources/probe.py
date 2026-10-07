"""Скелет адаптера порта ``HealthProber`` (T6; прямые HTTP health-probes).

Наполняется в P2 (стратегия Q6): только HTTP GET, таймауты по конфигу
манифеста (§8.2). Пока тела методов — заглушки.
"""

from __future__ import annotations


class ProbeAdapter:
    """Адаптер порта ``HealthProber`` (наполняется в P2)."""

    def probe(self, service: str) -> object:
        """HTTP health-probe сервиса — заготовка; наполняется в P2."""
        raise NotImplementedError("HealthProber.probe() наполняется в P2")
