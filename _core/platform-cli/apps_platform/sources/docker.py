"""Обёртка над ``legacy_cli.get_service_status()`` + заготовка порта ``DockerReader`` (T6).

Статус compose-сервиса в P1 — делегирование v1-функции с конверсией
``typer.Exit`` в ``PlatformError``; методы порта ``DockerReader`` (inspect,
статусы, stats, logs) наполняются в P2/P4 (§4). Логика из v1 не переносится.
"""

from __future__ import annotations

from pathlib import Path

from apps_platform import legacy_cli
from apps_platform.core.errors import PlatformError, wrap_unexpected

#: ``typer.Exit`` v1 доступен только через ``legacy_cli`` (импорт Typer в ``sources/`` запрещён).
_Exit = legacy_cli.typer.Exit


def get_service_status(service_path: Path) -> str:
    """Статус сервиса (``running/stopped/error/...``) — делегат ``legacy_cli.get_service_status``.

    Raises:
        PlatformError: при отказе резолвинга конфига (``typer.Exit`` v1,
            exit 3 → ``config_not_found``; прочие → ``internal_error``).
    """
    try:
        return legacy_cli.get_service_status(service_path)
    except _Exit as exc:
        if exc.exit_code == 3:
            raise PlatformError(
                code="config_not_found",
                message="Статус сервиса недоступен: конфигурация проекта не прочитана.",
                object=str(service_path),
                cause=exc,
            ) from exc
        raise wrap_unexpected(exc) from exc


class DockerAdapter:
    """Адаптер порта ``DockerReader`` (методы наполняются в P2: статусы/inspect)."""

    def inspect(self, service: str) -> object:
        """Inspect контейнеров сервиса — заготовка; наполняется в P2."""
        raise NotImplementedError("DockerReader.inspect() наполняется в P2")
