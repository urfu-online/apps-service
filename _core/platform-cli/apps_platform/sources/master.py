"""Обёртка над ``api_client`` (v1, aiohttp) — адаптер порта ``MasterGateway`` (T6).

Без rewrite: клиент v1 остаётся до P2 (§18.1: деградация и переход на
requests). Сессии не открываются при импорте — фабрика ``get_api_client()``
вызывается только из методов, наполняемых в P2.
"""

from __future__ import annotations

from apps_platform import api_client


class MasterAdapter:
    """Адаптер порта ``MasterGateway`` (наполняется в P2: деградация, rewrite → requests)."""

    #: Фабрика v1-клиента; вызывается лениво — при импорте сессия не открывается.
    _client_factory = staticmethod(api_client.get_api_client)

    def info(self) -> object:
        """Отчёт Master (``info``) — заготовка; наполняется в P2."""
        raise NotImplementedError("MasterGateway.info() наполняется в P2")
