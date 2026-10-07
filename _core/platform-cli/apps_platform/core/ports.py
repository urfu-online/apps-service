"""Закрытый список из 8 портов platform-cli v2 (ADR-002; §10.2–§10.3 спеки).

Порты — единственная граница между доменом (``core/``) и I/O-адаптерами
(``sources/``): тесты подменяют порты через ``Ctx``, а не имена helper'ов
(§10.2). Список портов **закрыт**: новый порт добавляется только через
ADR-ревью; новые методы появляются в существующих портах по мере появления
реального use case (§10.2 — порт только на реальной границе).

Список (таблица §4 tech spec P1):

1. ``ServiceDiscovery``  — полный контракт P1, адаптер ``sources/filesystem.py``;
2. ``DockerReader``      — заготовка, адаптер ``sources/docker.py``;
3. ``CaddyReader``       — заготовка, адаптер ``sources/caddy.py``;
4. ``MasterGateway``     — заготовка, адаптер ``sources/master.py``;
5. ``HealthProber``      — заготовка, адаптер ``sources/probe.py``;
6. ``LockManager``       — заготовка, адаптер ``sources/locks.py``;
7. ``CacheStore``        — заготовка, адаптер ``sources/cache.py``;
8. ``Journal``           — заготовка, адаптер ``sources/journal.py``.

Модуль зависит только от ``typing`` и ``core.models``: никаких Typer, Rich,
docker SDK, requests/aiohttp (доменный слой не знает об инфраструктуре,
§10.2). Выполняется тестом ``tests/test_ports.py``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import ServiceRef


@runtime_checkable
class ServiceDiscovery(Protocol):
    """Порт discovery сервисов: адаптер ``sources/filesystem.py`` (обёртка над v1 ``get_services()``).

    Полный контракт P1 (§4 tech spec): структурированный возврат ``ServiceRef``
    наполняется в P2 (§10.5).
    """

    def list_services(self) -> list[ServiceRef]:
        """Все сервисы проекта (``services/{public,internal}`` + ядро) как ``ServiceRef``."""
        ...


@runtime_checkable
class DockerReader(Protocol):
    """Порт чтения состояния Docker: адаптер ``sources/docker.py`` (обёртка над ``service_inspection``).

    Заготовка: наполняется в P2/P4 (статусы, inspect — P2; stats, logs — P4).
    """

    def inspect(self, service: str) -> object: ...


@runtime_checkable
class CaddyReader(Protocol):
    """Порт чтения конфигурации Caddy: адаптер ``sources/caddy.py`` (обёртка над ``caddy_parser``).

    Заготовка: наполняется в P2.
    """

    def routes(self) -> object: ...


@runtime_checkable
class MasterGateway(Protocol):
    """Порт Master API: адаптер ``sources/master.py`` (обёртка над ``api_client``).

    Заготовка: наполняется в P2 (деградация, rewrite на requests, §18.1 P2).
    """

    def info(self) -> object: ...


@runtime_checkable
class HealthProber(Protocol):
    """Порт HTTP health-probe: адаптер ``sources/probe.py``.

    Заготовка: наполняется в P2 (стратегия Q6).
    """

    def probe(self, service: str) -> object: ...


@runtime_checkable
class LockManager(Protocol):
    """Порт файловых lock'ов: адаптер ``sources/locks.py`` (обёртка над v1 ``platform_lock()``).

    Заготовка: наполняется в P3 (scoped locks, §13.4).
    """

    def acquire(self, key: str) -> object: ...


@runtime_checkable
class CacheStore(Protocol):
    """Порт кэша снапшотов completion: адаптер ``sources/cache.py``.

    Заготовка: наполняется в P5 (completion snapshots, §14).
    """

    def get(self, key: str) -> object: ...


@runtime_checkable
class Journal(Protocol):
    """Порт журнала операций: адаптер ``sources/journal.py``.

    Заготовка: наполняется в P4 (журнал операций, §13.5).
    """

    def record(self, event: str) -> object: ...
