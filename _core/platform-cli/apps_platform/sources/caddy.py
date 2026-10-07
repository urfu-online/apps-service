"""Скелет адаптера порта ``CaddyReader`` (T6; обёртка над ``caddy_parser``).

Парсер ``caddy_parser.parse_caddy_config`` остаётся в v1; чтение фактической
конфигурации Caddy подключается в P2 (§4), логика из v1 не переносится.
"""

from __future__ import annotations


class CaddyAdapter:
    """Адаптер порта ``CaddyReader`` (наполняется в P2)."""

    def routes(self) -> object:
        """Маршруты Caddy — заготовка; наполняется в P2."""
        raise NotImplementedError("CaddyReader.routes() наполняется в P2")
