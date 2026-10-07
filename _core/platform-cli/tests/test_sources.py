"""Тесты адаптеров ``apps_platform/sources`` (T6).

Критерии приёмки T6:

- каждый из 8 адаптеров реализует свой порт (``isinstance`` по
  ``runtime_checkable``-протоколам ``core/ports.py``) — сборка fake-``Ctx``;
- ``FilesystemDiscovery.list_services()`` возвращает ``ServiceRef`` с
  visibility по пути на tmp-структуре ``services/{public,internal}`` + ``_core``;
- обёртки конвертируют ``typer.Exit``/``FileNotFoundError`` v1 → ``PlatformError``;
- скелеты и заготовки бросают ``NotImplementedError``;
- AST-гигиена ``sources/*.py``: без импортов Typer/Rich/click, без ``print(``,
  без ``apps_platform.cli``/``commands``, ``legacy_cli`` — только в модулях-обёртках.
"""

from __future__ import annotations

import ast
import inspect
import re
from contextlib import contextmanager
from pathlib import Path

import pytest
import typer

from apps_platform import legacy_cli
from apps_platform.core import ports
from apps_platform.core.errors import PlatformError
from apps_platform.core.models import ServiceRef, Visibility
from apps_platform.sources import compose as compose_source
from apps_platform.sources import docker as docker_source
from apps_platform.sources.cache import CacheAdapter
from apps_platform.sources.caddy import CaddyAdapter
from apps_platform.sources.docker import DockerAdapter
from apps_platform.sources.filesystem import FilesystemDiscovery
from apps_platform.sources.journal import JournalAdapter
from apps_platform.sources.locks import LocksManager
from apps_platform.sources.master import MasterAdapter
from apps_platform.sources.probe import ProbeAdapter

#: Адаптер (реализация порта) для fake-сборки Ctx: поле Ctx → порт.
ADAPTER_CASES = [
    ("discovery", FilesystemDiscovery(), ports.ServiceDiscovery),
    ("docker", DockerAdapter(), ports.DockerReader),
    ("caddy", CaddyAdapter(), ports.CaddyReader),
    ("master", MasterAdapter(), ports.MasterGateway),
    ("prober", ProbeAdapter(), ports.HealthProber),
    ("locks", LocksManager(), ports.LockManager),
    ("cache", CacheAdapter(), ports.CacheStore),
    ("journal", JournalAdapter(), ports.Journal),
]

#: Модули ``sources/``, которым разрешён импорт ``legacy_cli`` (обёртки над v1).
WRAPPER_MODULES = frozenset({"filesystem.py", "compose.py", "docker.py", "locks.py"})

#: Ровно 10 модулей пакета (T6: __init__ + 9 адаптеров/обёрток).
EXPECTED_MODULES = frozenset(
    {
        "__init__.py",
        "filesystem.py",
        "compose.py",
        "docker.py",
        "locks.py",
        "master.py",
        "caddy.py",
        "probe.py",
        "cache.py",
        "journal.py",
    }
)

#: Внешние библиотеки, запрещённые в ``sources/*`` (вывод/CLI — только cli.py и ui/).
FORBIDDEN_IMPORT_ROOTS = frozenset({"typer", "rich", "click"})

#: Заготовки портов: тело метода → ``NotImplementedError``, docstring — фаза наполнения.
STUB_CALLS = [
    (DockerAdapter(), "inspect", ("svc",)),
    (CaddyAdapter(), "routes", ()),
    (MasterAdapter(), "info", ()),
    (ProbeAdapter(), "probe", ("svc",)),
    (CacheAdapter(), "get", ("key",)),
    (JournalAdapter(), "record", ("deployed svc",)),
    (LocksManager(), "acquire", ("global",)),
]


def _sources_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "apps_platform" / "sources"


def _sources_files() -> list[Path]:
    return sorted(_sources_dir().glob("*.py"))


def test_sources_package_contains_exactly_ten_modules() -> None:
    """Пакет sources/ ровно из 10 файлов — состав фиксирован бэклогом T6."""
    assert {path.name for path in _sources_files()} == EXPECTED_MODULES


@pytest.mark.parametrize(
    ("field", "adapter", "port"),
    ADAPTER_CASES,
    ids=[f"{field}-{port.__name__}" for field, _adapter, port in ADAPTER_CASES],
)
def test_adapter_satisfies_its_port(field: str, adapter: object, port: type) -> None:
    """Каждый адаптер проходит isinstance-проверку своего runtime_checkable-порта (fake-Ctx)."""
    assert isinstance(adapter, port), f"{field}: {type(adapter).__name__} не реализует {port.__name__}"


def test_fake_ctx_assembles_all_eight_adapters() -> None:
    """Словарь адаптеров в стиле Ctx содержит все 8 и каждое значение — реализация порта."""
    fake_ctx = {field: adapter for field, adapter, _port in ADAPTER_CASES}
    assert set(fake_ctx) == {"discovery", "docker", "caddy", "master", "prober", "locks", "cache", "journal"}
    assert isinstance(fake_ctx["discovery"], ports.ServiceDiscovery)
    assert isinstance(fake_ctx["docker"], ports.DockerReader)
    assert isinstance(fake_ctx["caddy"], ports.CaddyReader)
    assert isinstance(fake_ctx["master"], ports.MasterGateway)
    assert isinstance(fake_ctx["prober"], ports.HealthProber)
    assert isinstance(fake_ctx["locks"], ports.LockManager)
    assert isinstance(fake_ctx["cache"], ports.CacheStore)
    assert isinstance(fake_ctx["journal"], ports.Journal)


def _make_project(root: Path) -> None:
    """tmp-структура проекта: core + public + internal сервисы с compose-файлами."""
    for rel in ("services/public/svc1", "services/internal/svc2", "_core/master"):
        svc_dir = root / rel
        svc_dir.mkdir(parents=True)
        (svc_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")


@pytest.fixture
def project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Корень tmp-проекта, подставленный в v1-резолвинг (патчим legacy_cli, не internals sources)."""
    _make_project(tmp_path)
    monkeypatch.setattr(legacy_cli, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        legacy_cli,
        "get_config",
        lambda: {"core_path": "_core", "services_path": "services"},
    )
    return tmp_path


def test_list_services_returns_servicerefs_with_visibility_by_path(project_root: Path) -> None:
    """``list_services()`` — 3 ``ServiceRef``: visibility по пути, routing пока None (P2)."""
    refs = FilesystemDiscovery().list_services()

    assert len(refs) == 3
    assert all(isinstance(ref, ServiceRef) for ref in refs)
    by_name = {ref.name: ref for ref in refs}
    assert set(by_name) == {"svc1", "svc2", "master"}

    assert by_name["svc1"].visibility is Visibility.PUBLIC
    assert by_name["svc1"].path == project_root / "services" / "public" / "svc1"
    assert by_name["svc2"].visibility is Visibility.INTERNAL
    assert by_name["svc2"].path == project_root / "services" / "internal" / "svc2"
    assert by_name["master"].visibility is Visibility.CORE
    assert by_name["master"].path == project_root / "_core" / "master"

    assert all(ref.routing is None for ref in refs)
    assert all(ref.path.is_dir() for ref in refs)


def test_list_services_converts_typer_exit_config_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Отказ резолвинга конфига в v1 (typer.Exit(3)) → PlatformError(config_not_found), exit 3."""

    def _boom() -> dict[str, dict[str, object]]:
        raise typer.Exit(3)

    monkeypatch.setattr(legacy_cli, "get_services", _boom)
    with pytest.raises(PlatformError) as excinfo:
        FilesystemDiscovery().list_services()

    assert excinfo.value.code == "config_not_found"
    assert excinfo.value.exit_code == 3


def test_list_services_converts_unexpected_typer_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Прочий typer.Exit из v1 → PlatformError(internal_error), exit 1."""

    def _boom() -> dict[str, dict[str, object]]:
        raise typer.Exit(1)

    monkeypatch.setattr(legacy_cli, "get_services", _boom)
    with pytest.raises(PlatformError) as excinfo:
        FilesystemDiscovery().list_services()

    assert excinfo.value.code == "internal_error"
    assert excinfo.value.exit_code == 1


def test_run_compose_delegates_to_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    """``run_compose`` делигирует аргументы и dry_run в ``legacy_cli.compose_cmd`` без переписывания."""
    captured: list[tuple[Path, tuple[str, ...], bool]] = []

    def _fake(service_path: Path, *args: str, dry_run: bool = False) -> object:
        captured.append((service_path, args, dry_run))
        return "sentinel"

    monkeypatch.setattr(legacy_cli, "compose_cmd", _fake)
    result = compose_source.run_compose(Path("/srv/svc1"), "up", "-d", dry_run=True)

    assert result == "sentinel"
    assert captured == [(Path("/srv/svc1"), ("up", "-d"), True)]


def test_run_compose_converts_typer_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """typer.Exit(3) из ``compose_cmd`` → PlatformError(config_not_found), exit 3."""

    def _boom(*_args: object, **_kwargs: object) -> object:
        raise typer.Exit(3)

    monkeypatch.setattr(legacy_cli, "compose_cmd", _boom)
    with pytest.raises(PlatformError) as excinfo:
        compose_source.run_compose(Path("/srv/svc1"), "up")

    assert excinfo.value.code == "config_not_found"
    assert excinfo.value.exit_code == 3


def test_run_compose_converts_filedirectory_error_to_docker_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Отсутствие бинаря docker (FileNotFoundError) → PlatformError(docker_unavailable), exit 3."""

    def _boom(*_args: object, **_kwargs: object) -> object:
        raise FileNotFoundError(2, "No such file or directory", "docker")

    monkeypatch.setattr(legacy_cli, "compose_cmd", _boom)
    with pytest.raises(PlatformError) as excinfo:
        compose_source.run_compose(Path("/srv/svc1"), "up", "-d")

    assert excinfo.value.code == "docker_unavailable"
    assert excinfo.value.exit_code == 3


def test_get_service_status_delegates_to_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    """``get_service_status`` — чистый делегат ``legacy_cli.get_service_status``."""
    monkeypatch.setattr(legacy_cli, "get_service_status", lambda _path: "running (2)")
    assert docker_source.get_service_status(Path("/srv/svc1")) == "running (2)"


def test_get_service_status_converts_typer_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """typer.Exit из ``get_service_status`` → PlatformError (тип ошибки конвертируется)."""

    def _boom(_path: Path) -> str:
        raise typer.Exit(1)

    monkeypatch.setattr(legacy_cli, "get_service_status", _boom)
    with pytest.raises(PlatformError) as excinfo:
        docker_source.get_service_status(Path("/srv/svc1"))

    assert excinfo.value.code == "internal_error"
    assert excinfo.value.exit_code == 1


def test_lock_hold_converts_typer_exit_to_lock_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Занятость lock'а (typer.Exit из platform_lock) → PlatformError(lock_busy), exit 3."""

    @contextmanager
    def _busy(*, blocking: bool = False, timeout: float = 0.0):
        raise typer.Exit(1)
        yield  # pragma: no cover — делает функцию-генератором для @contextmanager

    monkeypatch.setattr(legacy_cli, "platform_lock", _busy)
    with pytest.raises(PlatformError) as excinfo, LocksManager().hold():
        pass

    assert excinfo.value.code == "lock_busy"
    assert excinfo.value.exit_code == 3


def test_lock_hold_does_not_convert_body_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Исключения тела ``with`` не конвертируются — конверсируется только захват lock'а."""

    @contextmanager
    def _ok(*, blocking: bool = False, timeout: float = 0.0):
        yield

    monkeypatch.setattr(legacy_cli, "platform_lock", _ok)
    with pytest.raises(ValueError, match="boom"), LocksManager().hold():
        raise ValueError("boom")


@pytest.mark.parametrize(
    ("adapter", "method", "args"),
    STUB_CALLS,
    ids=[f"{type(adapter).__name__}.{method}" for adapter, method, _args in STUB_CALLS],
)
def test_skeleton_methods_raise_not_implemented(adapter: object, method: str, args: tuple[str, ...]) -> None:
    """Заготовки портов (docker.inspect, master.info, locks.acquire, …) — NotImplementedError."""
    with pytest.raises(NotImplementedError):
        getattr(adapter, method)(*args)


@pytest.mark.parametrize(
    "adapter",
    [
        DockerAdapter(),
        CaddyAdapter(),
        MasterAdapter(),
        ProbeAdapter(),
        CacheAdapter(),
        JournalAdapter(),
        LocksManager(),
    ],
    ids=lambda value: type(value).__name__,
)
def test_skeleton_docstrings_declare_phase(adapter: object) -> None:
    """Docstring каждого скелета указывает фазу наполнения «наполняется(ются) в Pn»."""
    doc = inspect.getdoc(adapter) or ""
    assert re.search(r"наполн\w* в P\d", doc), f"{type(adapter).__name__}: в docstring нет фазы наполнения"


def _import_facts(path: Path) -> tuple[set[str], set[str], set[str], list[ast.Call]]:
    """AST-факты файла: корневые имена, полные имена, имена из ``from apps_platform import`` и вызовы print."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    modules: set[str] = set()
    from_apps_platform: set[str] = set()
    print_calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
            modules.add(node.module)
            if node.module == "apps_platform":
                from_apps_platform.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Call):
            is_name_print = isinstance(node.func, ast.Name) and node.func.id == "print"
            is_attr_print = isinstance(node.func, ast.Attribute) and node.func.attr == "print"
            if is_name_print or is_attr_print:
                print_calls.append(node)
    return roots, modules, from_apps_platform, print_calls


def test_sources_have_no_typer_rich_imports_and_no_print() -> None:
    """Ни один ``sources/*.py`` не импортирует Typer/Rich/click и не делает print/console.print."""
    for path in _sources_files():
        roots, _modules, _from_apps, print_calls = _import_facts(path)
        forbidden = roots & FORBIDDEN_IMPORT_ROOTS
        assert not forbidden, f"{path.name}: запрещённые импорты {sorted(forbidden)}"
        assert not print_calls, f"{path.name}: запрещён вызов print/print-атрибута"


def test_sources_do_not_import_v2_cli_or_commands() -> None:
    """Ни один ``sources/*.py`` не импортирует ``apps_platform.cli`` (v2) и ``apps_platform.commands``."""
    for path in _sources_files():
        _roots, modules, from_apps_platform, _prints = _import_facts(path)
        assert "apps_platform.cli" not in modules, f"{path.name}: импорт apps_platform.cli запрещён"
        assert not any(name.startswith("apps_platform.commands") for name in modules), path.name
        assert "cli" not in from_apps_platform, f"{path.name}: 'from apps_platform import cli' запрещён"
        assert "commands" not in from_apps_platform, f"{path.name}: 'from apps_platform import commands' запрещён"


def test_legacy_cli_imported_only_in_wrapper_modules() -> None:
    """``legacy_cli`` импортируют только обёртки (filesystem, compose, docker, locks) — не скелеты."""
    for path in _sources_files():
        _roots, modules, from_apps_platform, _prints = _import_facts(path)
        has_legacy = "apps_platform.legacy_cli" in modules or "legacy_cli" in from_apps_platform
        assert has_legacy == (
            path.name in WRAPPER_MODULES
        ), f"{path.name}: legacy_cli импортирован={has_legacy}, разрешено={path.name in WRAPPER_MODULES}"
