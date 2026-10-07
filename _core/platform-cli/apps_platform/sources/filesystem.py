"""Адаптер ``ServiceDiscovery``: обёртка над ``legacy_cli.get_services()`` (T6).

Сканирование каталогов остаётся в v1 (``legacy_cli.get_services``) до P2
(§10.5): здесь только конвертация ``dict`` → ``list[ServiceRef]`` и перевод
отказа конфигурации (``typer.Exit``) в ``PlatformError``. Резолвинг корня и
ops-конфига идёт через делегаты v1 в ``config.py`` (T4); вывода модуль не
делает — печать ошибки в v1-функции остаётся её ответственностью.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from apps_platform import legacy_cli
from apps_platform.core.errors import PlatformError, wrap_unexpected
from apps_platform.core.models import ServiceRef, Visibility

#: ``typer.Exit`` v1 доступен только через ``legacy_cli`` (импорт Typer в ``sources/`` запрещён).
_Exit = legacy_cli.typer.Exit

_TYPE_TO_VISIBILITY: Mapping[str, Visibility] = {
    "public": Visibility.PUBLIC,
    "internal": Visibility.INTERNAL,
    "core": Visibility.CORE,
}


def _visibility(path: Path, entry: Mapping[str, Any]) -> Visibility:
    """Видимость сервиса по его пути (§5.2): ``services/{public,internal}`` → public/internal, ``_core`` → core.

    Нестандартные ``core_path``/``services_path`` из ops-конфига (путь не
    совпадает с раскладкой по умолчанию) резолвятся по типу каталога,
    посчитанному v1 при скане (``get_services()["type"]``).
    """
    parent = path.parent.name
    if parent in _TYPE_TO_VISIBILITY:
        return _TYPE_TO_VISIBILITY[parent]
    if parent == "_core":
        return Visibility.CORE
    return _TYPE_TO_VISIBILITY[str(entry.get("type", ""))]


class FilesystemDiscovery:
    """Адаптер порта ``ServiceDiscovery`` (обёртка над v1 ``get_services``).

    ``routing`` пока ``None``: разбор манифеста и маршрутов — P2 (§10.5).
    """

    def list_services(self) -> list[ServiceRef]:
        """Все сервисы проекта как ``ServiceRef`` (порядок v1: core, public, internal)."""
        try:
            services = legacy_cli.get_services()
        except _Exit as exc:
            # v1 печатает текст сам и сигналит typer.Exit; единственный
            # реальный отказ здесь — резолвинг конфига (exit 3, §11.2 ФС → 3).
            if exc.exit_code == 3:
                raise PlatformError(
                    code="config_not_found",
                    message="Список сервисов недоступен: конфигурация проекта не прочитана.",
                    cause=exc,
                ) from exc
            raise wrap_unexpected(exc) from exc
        return [
            ServiceRef(
                name=name,
                path=Path(entry["path"]),
                visibility=_visibility(Path(entry["path"]), entry),
                routing=None,
            )
            for name, entry in services.items()
        ]
