"""Обёртка над ``legacy_cli.compose_cmd()``: запуск docker compose (T6).

Сборка argv, передача ``.env`` и ``dry_run`` остаются в v1 до P3 (§10.5);
здесь — конвертация отказов в ``PlatformError``: отсутствие бинаря docker
(``FileNotFoundError``) → ``docker_unavailable`` (exit 3, §11.2/§12.4),
отказ резолвинга конфига (``typer.Exit``) → ``config_not_found``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from apps_platform import legacy_cli
from apps_platform.core.errors import PlatformError, wrap_unexpected

if TYPE_CHECKING:
    import subprocess

#: ``typer.Exit`` v1 доступен только через ``legacy_cli`` (импорт Typer в ``sources/`` запрещён).
_Exit = legacy_cli.typer.Exit


def run_compose(service_path: Path, *args: str, dry_run: bool = False) -> subprocess.CompletedProcess[Any]:
    """Выполнить ``docker compose`` для каталога сервиса — делегат ``legacy_cli.compose_cmd``.

    Args:
        service_path: каталог сервиса (в нём ``docker-compose.yml``).
        *args: аргументы compose (``up -d``, ``pull`` …).
        dry_run: только показать команду, не выполняя её.

    Raises:
        PlatformError: ``docker_unavailable`` — docker не найден в PATH;
            ``config_not_found`` — не прочитан корень/конфиг проекта.
    """
    try:
        return legacy_cli.compose_cmd(service_path, *args, dry_run=dry_run)
    except FileNotFoundError as exc:
        raise PlatformError(
            code="docker_unavailable",
            message=f"Docker недоступен: {exc}",
            object=str(service_path),
            cause=exc,
        ) from exc
    except _Exit as exc:
        if exc.exit_code == 3:
            raise PlatformError(
                code="config_not_found",
                message="docker compose не запущен: конфигурация проекта не прочитана.",
                object=str(service_path),
                cause=exc,
            ) from exc
        raise wrap_unexpected(exc) from exc
