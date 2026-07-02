"""
CLI утилита для управления платформой Platform Master Service
"""

import fcntl
import logging
import os
import re
import subprocess
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any

import docker
import requests  # noqa: F401  # re-exported for ``patch("apps_platform.cli.requests.get")`` в тестах
import typer
import yaml
from rich.console import Console
from rich.table import Table  # noqa: F401  # re-exported для команд из ``commands.*``

from apps_platform.api_client import APIClient as BackupAPIClient  # noqa: F401

# Ре-экспорт хелперов из ``service_inspection`` для обратной совместимости
# (тесты патчат их как ``apps_platform.cli._<helper>``). Тяжёлые функции вынесены
# из cli.py в Шаге 8, чтобы удержать файл в пределах 500 строк.
from apps_platform.service_inspection import (  # noqa: F401
    DOCKER_TIMEOUT,
    _expand_env_vars,
    _get_actual_service_urls,
    _get_all_container_statuses,
    _matches_service,
    _parse_caddy_config,
    _parse_compose_port_mapping,
)

app = typer.Typer(
    name="platform",
    help="CLI утилита для управления платформой Platform Master Service",
    add_completion=False,
)
console = Console()
logger = logging.getLogger(__name__)

# Константы
MAX_URLS_DISPLAY = 3
AVAILABILITY_TIMEOUT = 3
CADDY_DEFAULT_CONTAINER_NAME = "caddy"
REQUEST_TIMEOUT = 10

SERVICE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")

# Маркер корня проекта (закоммитирован в репозитории). Ищется вверх от CWD,
# чтобы CLI работал из любой поддиректории без явного указания корня.
_PROJECT_ROOT_MARKER = ".ops-root"

# Кандидаты системного конфига (приоритет сверху вниз). В production
# используется /etc/ops-manager/config.yml; канонический путь установки /apps
# и per-user конфиг служат fallback'ом для дев-окружения.
_SYSTEM_CONFIG_PATHS = (
    Path("/etc/ops-manager/config.yml"),
    Path("/apps/.ops-config.yml"),
    Path.home() / ".config" / "ops-manager" / "config.yml",
)


def _configure_logging(*, verbose: bool) -> None:
    """Настраивает логирование для CLI.

    По умолчанию выводим только WARNING/ERROR, чтобы не мешать обычному использованию.
    Флаг `--verbose` включает DEBUG для диагностики.
    """

    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    # Сторонние библиотеки не должны спамить при --verbose.
    logging.getLogger("urllib3").setLevel(logging.WARNING)


@app.callback()
def _main_callback(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Включить отладочную информацию (logging DEBUG).",
    ),
) -> None:
    _configure_logging(verbose=verbose)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Рекурсивное слияние словарей конфигурации."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _find_marker_root(start: Path) -> Path | None:
    """Поиск корня проекта вверх от `start` по маркеру `.ops-root`.

    Маркер коммитится в репозиторий и однозначно идентифицирует корень проекта,
    в отличие от `.ops-config.yml`, который может встречаться во вложенных сервисах.
    """
    current = start.resolve()
    for parent in [current, *current.parents]:
        if (parent / _PROJECT_ROOT_MARKER).exists():
            return parent
    return None


def _read_config_file(cfg_path: Path) -> dict[str, Any]:
    """Чтение YAML-конфига с применением .local-переопределения."""
    with open(cfg_path) as f:
        config: dict[str, Any] = yaml.safe_load(f) or {}
    local_override = cfg_path.parent / ".ops-config.local.yml"
    if local_override.exists():
        with open(local_override) as f:
            local_data: dict[str, Any] = yaml.safe_load(f) or {}
        _deep_merge(config, local_data)
    return config


@lru_cache(maxsize=1)
def get_project_root() -> Path:
    """Резолвинг корня проекта по приоритетной цепочке.

    Порядок разрешения (первый найденный выигрывает):
      1. `OPS_PROJECT_ROOT` env — явное переопределение (dev/CI);
      2. маркер `.ops-root`, ищется вверх от CWD — работа из поддиректорий (dev);
      3. `project_root` из системного конфига — production, единый источник правды;
      4. `Path.cwd()` — последний рубеж (поведение совместимо со старыми версиями).

    Результат кэшируется на время процесса. CLI корректно работает из любой
    директории и для любого пользователя без изменения настроек.
    """
    # 1. Явное переопределение через env — авторитарное: если задано, оно обязано
    #    быть валидным. Опечатка/устаревшее значение не должны молча увести CLI
    #    на чужой корень.
    if env_root := os.getenv("OPS_PROJECT_ROOT"):
        root = Path(env_root)
        if root.is_dir():
            logger.debug("PROJECT_ROOT from OPS_PROJECT_ROOT env: %s", root)
            return root
        console.print(
            f"[red]❌ OPS_PROJECT_ROOT={env_root} не является существующей директорией. "
            "Исправьте переменную или снимите её, чтобы авто-резолвинг сработал.[/red]"
        )
        raise typer.Exit(1)

    # 2. Поиск маркера вверх от текущей директории (dev).
    if marker_root := _find_marker_root(Path.cwd()):
        logger.debug("PROJECT_ROOT from marker %s: %s", _PROJECT_ROOT_MARKER, marker_root)
        return marker_root

    # 3. Значение project_root из системного конфига (production).
    for cfg_path in _SYSTEM_CONFIG_PATHS:
        if not cfg_path.exists():
            continue
        try:
            cfg = _read_config_file(cfg_path)
        except OSError:
            continue
        if pr := cfg.get("project_root"):
            root = Path(pr)
            if root.is_dir():
                logger.debug("PROJECT_ROOT from system config %s: %s", cfg_path, root)
                return root

    # 4. Fallback на текущую директорию.
    logger.debug("PROJECT_ROOT fallback to cwd: %s", Path.cwd())
    return Path.cwd()


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    """Загрузка конфигурации — кэшируется на время процесса.

    Порядок поиска конфига:
      1. `OPS_CONFIG_PATH` env — явное переопределение;
      2. `.ops-config.yml` относительно резолвленного корня проекта;
      3. системные кандидаты (`/etc/ops-manager`, `/apps`, per-user).
    """
    root = get_project_root()
    config_candidates: list[Path] = [
        Path(os.getenv("OPS_CONFIG_PATH", root / ".ops-config.yml")),
        *_SYSTEM_CONFIG_PATHS,
    ]
    seen: set[Path] = set()
    for cfg_path in config_candidates:
        cfg_path = Path(cfg_path)
        if cfg_path in seen or not cfg_path.exists():
            continue
        seen.add(cfg_path)
        try:
            return _read_config_file(cfg_path)
        except OSError as e:
            logger.warning("Cannot read config %s: %s", cfg_path, e)

    console.print("[red]❌ Конфиг не найден. Запустите ./install.sh или укажите OPS_CONFIG_PATH[/red]")
    raise typer.Exit(1)


@contextmanager
def docker_client() -> Iterator[Any]:
    """Контекстный менеджер для Docker client."""
    client = docker.from_env()
    try:
        yield client
    finally:
        client.close()


def _parse_bool_env(var_name: str, default: bool = True) -> bool:
    """Парсер булевой переменной окружения.

    Поддерживает значения: 1/0, true/false, yes/no, on/off (без учёта регистра).
    """
    raw = os.getenv(var_name)
    if raw is None:
        return default

    value = raw.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _get_ssl_verify(*, insecure: bool) -> bool:
    """Возвращает значение параметра requests.verify.

    - В production (PLATFORM_ENV=production) всегда verify=True и флаг --insecure игнорируется
    - В остальных окружениях verify включено по умолчанию (безопасное поведение)
    - Может быть отключено через PLATFORM_SSL_VERIFY=false
    - Флаг --insecure имеет приоритет и отключает верификацию (кроме production)
    """

    platform_env = os.getenv("PLATFORM_ENV", "").strip().lower()
    if platform_env == "production":
        if insecure:
            logger.warning("Ignoring --insecure because PLATFORM_ENV=production")
        return True

    if insecure:
        return False

    return _parse_bool_env("PLATFORM_SSL_VERIFY", default=True)


def get_services() -> dict[str, dict[str, Any]]:
    """Сканирование сервисов в проекте."""
    config = get_config()
    project_root = get_project_root()
    services: dict[str, dict[str, Any]] = {}
    core_path = project_root / config.get("core_path", "_core")
    services_path = project_root / config.get("services_path", "services")

    if core_path.exists():
        for svc_dir in core_path.iterdir():
            if svc_dir.is_dir() and (svc_dir / "docker-compose.yml").exists():
                services[svc_dir.name] = {"path": svc_dir, "type": "core"}

    for subdir in ["public", "internal"]:
        type_dir = services_path / subdir
        if type_dir.exists():
            for svc_dir in type_dir.iterdir():
                if svc_dir.is_dir() and (svc_dir / "docker-compose.yml").exists():
                    services[svc_dir.name] = {"path": svc_dir, "type": subdir}

    return services


def _lock_path() -> Path:
    """Путь к файлу-блокировке CLI (Шаг 17).

    Приоритет: ``$XDG_RUNTIME_DIR`` → ``/var/lock`` → ``tempfile.gettempdir()``.
    Использование ``$XDG_RUNTIME_DIR`` предпочтительно, т.к. блокировка
    привязана к сессии пользователя и очищается при logout.
    """
    xdg = os.getenv("XDG_RUNTIME_DIR")
    if xdg:
        return Path(xdg) / "platform-cli.lock"
    if os.access("/var/lock", os.W_OK):
        return Path("/var/lock/platform-cli.lock")
    return Path(tempfile.gettempdir()) / "platform-cli.lock"


@contextmanager
def platform_lock(*, blocking: bool = False, timeout: float = 0.0) -> Iterator[None]:
    """Файл-блокировка для предотвращения race conditions между CLI-вызовами.

    Реализация через ``fcntl.flock(LOCK_EX | LOCK_NB)`` — освобождается ОС
    при завершении процесса. По умолчанию ``non-blocking`` — если другая
    команда ``platform`` уже выполняется, текущая команда завершается с
    ``typer.Exit(1)`` и понятным сообщением.

    Args:
        blocking: если True — ожидать освобождения блокировки до ``timeout`` сек.
        timeout: максимальное время ожидания (только при ``blocking=True``).
    """
    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # O_NOFOLLOW refuses to open through a symlink. Lock paths live in shared
    # directories (/var/lock, /tmp) where untrusted local users can race us;
    # following a symlink would let them truncate arbitrary files we can write.
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        if blocking:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        console.print(
                            f"[red]❌ Таймаут ожидания блокировки {path} "
                            f"({timeout}s). Другая команда platform "
                            "уже выполняется.[/red]"
                        )
                        raise typer.Exit(1) from None
                    time.sleep(0.1)
        else:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                console.print(
                    f"[red]❌ Другая команда platform уже выполняется "
                    f"(lock: {path}).[/red]"
                )
                raise typer.Exit(1) from None
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except Exception:  # noqa: BLE001 — best effort
            pass
        os.close(fd)


def compose_cmd(
    service_path: Path,
    *args: str,
    dry_run: bool = False,
) -> subprocess.CompletedProcess[Any]:
    """Выполнение docker compose с явной передачей .env.

    Параметр ``dry_run=True`` возвращает фиктивный ``CompletedProcess`` с кодом
    0 и логирует команду, которую CLI выполнил бы в реальном режиме.
    Используется командами ``deploy``/``new`` для безопасного предпросмотра.
    """
    env_file = (get_project_root() / ".env").resolve()
    cmd = [
        "docker",
        "compose",
        "--project-directory",
        str(service_path),
        "-f",
        str(service_path / "docker-compose.yml"),
    ]
    if env_file.exists():
        cmd.extend(["--env-file", str(env_file)])
    cmd.extend(args)
    if dry_run:
        logger.info("[DRY-RUN] would execute: %s", " ".join(cmd))
        console.print(f"[yellow]DRY-RUN:[/yellow] {' '.join(cmd)}")
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
    return subprocess.run(cmd, capture_output=False)




def get_service_status(service_path: Path) -> str:
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", str(service_path / "docker-compose.yml"), "ps", "-q"],
            capture_output=True,
            text=True,
            cwd=service_path,
            timeout=DOCKER_TIMEOUT,
        )
        if result.returncode != 0:
            return f"error: {result.stderr.strip()[:50]}"
        containers = [c for c in result.stdout.strip().split("\n") if c]
        return "stopped" if not containers else f"running ({len(containers)})"
    except subprocess.TimeoutExpired:
        return "timeout"
    except FileNotFoundError:
        return "docker-not-found"
    except Exception as e:
        return f"error: {type(e).__name__}"


def get_service_or_fail(services: dict[str, dict[str, Any]], service_name: str) -> Path:
    """Проверка существования сервиса и возврат пути."""
    if service_name not in services:
        console.print(f"[red]❌ Сервис '{service_name}' не найден[/red]")
        raise typer.Exit(1)
    return services[service_name]["path"]


def validate_service_name(name: str) -> str:
    """Валидация имени сервиса.

    Правила (совместимо с Docker naming convention):
    - 1..128 символов
    - ^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$
    - дополнительно запрещаем path traversal/разделители путей
    """
    if not name:
        console.print("[red]❌ Некорректное имя сервиса[/red]")
        raise typer.Exit(1)

    if "/" in name or "\\" in name or ".." in name:
        console.print("[red]❌ Некорректное имя сервиса[/red]")
        raise typer.Exit(1)

    if not SERVICE_NAME_RE.fullmatch(name):
        console.print(
            "[red]❌ Некорректное имя сервиса. Допустимо: 1..128 символов, латиница/цифры/_.-; "
            "первый символ — буква или цифра.[/red]"
        )
        raise typer.Exit(1)
    return name.lower()


def _service_exists(service_name: str) -> bool:
    """Проверяет, существует ли сервис с указанным именем."""
    try:
        get_service_or_fail(get_services(), service_name)
        return True
    except typer.Exit:
        return False


def _get_backup_enabled(service_name: str) -> bool:
    """Возвращает True, если в service.yml сервиса включён раздел ``backup``."""
    try:
        service_path = get_service_or_fail(get_services(), service_name)
    except typer.Exit:
        return False

    service_yml_path = service_path / "service.yml"
    if not service_yml_path.exists():
        return False

    try:
        with open(service_yml_path) as f:
            service_config = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return False

    return bool(service_config.get("backup", {}).get("enabled", False))


# Импорт пакета команд нужен для регистрации @app.command-декораторов
# на ``apps_platform.cli.app``. Без этого ``platform list``, ``platform deploy``,
# ``platform backup ...`` и пр. будут отсутствовать в CLI.
from . import commands as _commands  # noqa: E402, F401


def main() -> None:
    """Точка входа CLI."""
    app()


if __name__ == "__main__":
    main()
