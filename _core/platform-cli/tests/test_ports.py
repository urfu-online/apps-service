"""Тесты портов core/ports.py (T3): 8 Protocols, runtime_checkable, чистые импорты (ADR-002)."""

from __future__ import annotations

import ast
import inspect
import typing
from pathlib import Path

import pytest

from apps_platform.core import ports
from apps_platform.core.models import ServiceRef, Visibility

#: Закрытый список портов ADR-002 — ровно 8, новых быть не может.
EXPECTED_PORTS = frozenset(
    {
        "ServiceDiscovery",
        "DockerReader",
        "CaddyReader",
        "MasterGateway",
        "HealthProber",
        "LockManager",
        "CacheStore",
        "Journal",
    }
)

#: Внешние библиотеки, которые core/ не имеет права импортировать (§10.2).
FORBIDDEN_IMPORTS = {"typer", "rich", "docker", "requests", "aiohttp", "click"}

#: Разрешённые абсолютные импорты ports.py — только typing (+ __future__).
ALLOWED_IMPORTS = {"__future__", "typing"}


class FakeServiceDiscovery:
    def list_services(self) -> list[ServiceRef]:
        return [
            ServiceRef(name="api", path=Path("services/public/api"), visibility=Visibility.PUBLIC),
            ServiceRef(name="worker", path=Path("services/internal/worker"), visibility=Visibility.INTERNAL),
        ]


class FakeDockerReader:
    def inspect(self, service: str) -> object:
        return {"service": service}


class FakeCaddyReader:
    def routes(self) -> object:
        return {}


class FakeMasterGateway:
    def info(self) -> object:
        return {}


class FakeHealthProber:
    def probe(self, service: str) -> object:
        return {"service": service}


class FakeLockManager:
    def acquire(self, key: str) -> object:
        return key


class FakeCacheStore:
    def get(self, key: str) -> object:
        return key


class FakeJournal:
    def record(self, event: str) -> object:
        return event


FAKE_IMPLEMENTATIONS = [
    (FakeServiceDiscovery, ports.ServiceDiscovery),
    (FakeDockerReader, ports.DockerReader),
    (FakeCaddyReader, ports.CaddyReader),
    (FakeMasterGateway, ports.MasterGateway),
    (FakeHealthProber, ports.HealthProber),
    (FakeLockManager, ports.LockManager),
    (FakeCacheStore, ports.CacheStore),
    (FakeJournal, ports.Journal),
]


def _ports_source_path() -> Path:
    return Path(inspect.getfile(ports))


def _ports_tree() -> ast.Module:
    return ast.parse(_ports_source_path().read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("fake_cls", "port"), FAKE_IMPLEMENTATIONS, ids=lambda value: getattr(value, "__name__", str(value))
)
def test_fake_implementation_satisfies_port(fake_cls: type, port: type) -> None:
    """Каждая fake-реализация проходит isinstance-проверку runtime_checkable-протокола."""
    fake = fake_cls()
    assert isinstance(fake, port)
    assert isinstance(port, type)


def test_non_implementation_does_not_satisfy_any_port() -> None:
    """runtime_checkable реально проверяет методы: пустой класс не проходит ни один порт."""

    class Empty:
        pass

    for _fake_cls, port in FAKE_IMPLEMENTATIONS:
        assert not isinstance(Empty(), port)


def test_every_port_is_runtime_checkable_protocol() -> None:
    """Все 8 портов — runtime_checkable-протоколы с минимум одним методом."""
    for name in EXPECTED_PORTS:
        proto = getattr(ports, name)
        assert getattr(proto, "_is_protocol", False) is True, name
        assert getattr(proto, "_is_runtime_protocol", False) is True, name
        assert getattr(proto, "__protocol_attrs__", set()), name


def test_exactly_eight_protocol_classes_declared() -> None:
    """В ports.py объявлено ровно 8 классов-протоколов (AST, классификация по базе Protocol)."""
    declared = {
        node.name
        for node in _ports_tree().body
        if isinstance(node, ast.ClassDef)
        and any(isinstance(base, ast.Name) and base.id == "Protocol" for base in node.bases)
    }
    assert declared == EXPECTED_PORTS
    assert len(declared) == 8


def test_exactly_eight_protocols_at_runtime() -> None:
    """Ровно 8 протоколов экспортируется модулем core.ports."""
    exported = {
        name
        for name, obj in vars(ports).items()
        if isinstance(obj, type) and getattr(obj, "_is_runtime_protocol", False)
    }
    assert exported == EXPECTED_PORTS
    assert len(exported) == 8


def test_ports_module_imports_are_clean() -> None:
    """AST-проверка импортов ports.py: только typing и core.models, без внешних библиотек (§10.2)."""
    tree = _ports_tree()
    roots: set[str] = set()
    relative: list[tuple[int, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    roots.add(node.module.split(".")[0])
            else:
                relative.append((node.level, node.module))
    source = _ports_source_path().name
    assert roots.isdisjoint(FORBIDDEN_IMPORTS), f"запрещённые импорты в {source}: {sorted(roots & FORBIDDEN_IMPORTS)}"
    assert roots <= ALLOWED_IMPORTS, f"неожиданные импорты в {source}: {sorted(roots - ALLOWED_IMPORTS)}"
    assert all(
        level == 1 and module == "models" for level, module in relative
    ), f"относительные импорты в {source} должны указывать только на .models: {relative}"


def test_serviceref_discovery_contract_signature() -> None:
    """ServiceDiscovery — полный контракт P1: list_services() -> list[ServiceRef]."""
    hints = typing.get_type_hints(ports.ServiceDiscovery.list_services)
    assert hints["return"] == list[ServiceRef]
    refs = FakeServiceDiscovery().list_services()
    assert refs and all(isinstance(ref, ServiceRef) for ref in refs)


def test_stub_ports_docstrings_declare_phase() -> None:
    """Каждая заготовка порта в docstring указывает фазу наполнения «наполняется в Pn»."""
    stubs = EXPECTED_PORTS - {"ServiceDiscovery"}
    for name in stubs:
        doc = inspect.getdoc(getattr(ports, name)) or ""
        assert "наполняется в P" in doc, f"{name}: в docstring нет фазы наполнения"
