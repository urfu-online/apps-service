"""
CLI утилита для управления платформой Platform Master Service
"""

import json
import logging
import os
import re
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any

import docker
import requests
import typer
import yaml
from rich.console import Console
from rich.table import Table

from apps_platform.caddy_parser import parse_caddy_config

app = typer.Typer(
    name="platform",
    help="CLI утилита для управления платформой Platform Master Service",
    add_completion=False,
)
console = Console()
logger = logging.getLogger(__name__)

# Глобальная конфигурация (инициализируется однократно при импорте)
PROJECT_ROOT = Path(os.getenv("OPS_PROJECT_ROOT", str(Path.cwd())))
CONFIG_FILE: Path | None = None

# Константы
MAX_URLS_DISPLAY = 3
AVAILABILITY_TIMEOUT = 3
CADDY_DEFAULT_CONTAINER_NAME = "caddy"
DOCKER_TIMEOUT = 10
REQUEST_TIMEOUT = 10

SERVICE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")


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


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    """Загрузка конфигурации — кэшируется на время процесса."""
    config_candidates: list[Path] = [
        Path(os.getenv("OPS_CONFIG_PATH", PROJECT_ROOT / ".ops-config.yml")),
        Path(__file__).resolve().parent.parent.parent.parent / ".ops-config.yml",
        Path.home() / ".config" / "ops-manager" / "config.yml",
    ]
    for cfg_path in config_candidates:
        cfg_path = Path(cfg_path)
        if cfg_path.exists():
            with open(cfg_path) as f:
                config = yaml.safe_load(f) or {}
            local_override = cfg_path.parent / ".ops-config.local.yml"
            if local_override.exists():
                with open(local_override) as f:
                    local_data = yaml.safe_load(f) or {}
                _deep_merge(config, local_data)
            return config

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
    services: dict[str, dict[str, Any]] = {}
    core_path = PROJECT_ROOT / config.get("core_path", "_core")
    services_path = PROJECT_ROOT / config.get("services_path", "services")

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


def compose_cmd(service_path: Path, *args: str) -> subprocess.CompletedProcess[Any]:
    """Выполнение docker compose с явной передачей .env."""
    env_file = (Path(__file__).resolve().parent.parent.parent.parent / ".env").resolve()
    cmd = [
        "docker", "compose",
        "--project-directory", str(service_path),
        "-f", str(service_path / "docker-compose.yml"),
    ]
    if env_file.exists():
        cmd.extend(["--env-file", str(env_file)])
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=False)


def _get_all_container_statuses() -> dict[str, str]:
    """Один запрос к Docker для получения статусов всех контейнеров."""
    try:
        # Используем JSON-формат для надёжного парсинга
        res = subprocess.run(
            ["docker", "ps", "-a", "--format", "json"],
            capture_output=True, text=True, check=True, timeout=DOCKER_TIMEOUT
        )
        statuses = {}
        for line in res.stdout.strip().splitlines():
            if not line:
                continue
            entry = json.loads(line)
            name = entry.get("Names", "")
            status = entry.get("Status", "")
            if name:
                statuses[name] = status
        return statuses
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {}


def _matches_service(container_name: str, service_name: str) -> bool:
    """Гибкое сопоставление имени контейнера и сервиса."""
    # Точное совпадение
    if container_name == service_name:
        return True
    # Docker Compose префиксы: {service}-frontend-1, {service}_db_1
    if container_name.startswith(f"{service_name}-") or container_name.startswith(f"{service_name}_"):
        return True
    # Project-name суффиксы: platform-master, backup_support_1
    if container_name.endswith(f"-{service_name}") or container_name.endswith(f"_{service_name}"):
        return True
    # Составные имена: course-archive-explorer в course-archive-explorer-backend-1
    if service_name in container_name:
        return True
    return False


def _get_container_network_info(container_name: str) -> dict[str, Any]:
    """Получение информации о сети контейнера (IP, порты)."""
    try:
        with docker_client() as client:
            container = client.containers.get(container_name)
            network_settings = container.attrs.get("NetworkSettings", {})
            is_running = container.status == "running"

        # Получаем IP адреса из сетей
        networks = network_settings.get("Networks", {})
        ip_addresses = []
        for net_name, net_config in networks.items():
            if net_config.get("IPAddress"):
                ip_addresses.append({
                    "network": net_name,
                    "ip": net_config["IPAddress"]
                })

        # Получаем опубликованные порты
        ports = network_settings.get("Ports", {})
        exposed_ports = []
        for port_key, port_bindings in ports.items():
            if port_bindings:
                for binding in port_bindings:
                    exposed_ports.append({
                        "container_port": port_key,
                        "host_ip": binding.get("HostIp", "0.0.0.0"),
                        "host_port": binding.get("HostPort")
                    })

        result: dict[str, Any] = {
            "ip_addresses": ip_addresses,
            "exposed_ports": exposed_ports,
            "running": is_running,
        }
        logger.debug("Container network info for %s: %s", container_name, result)
        return result
    except Exception:
        return {"ip_addresses": [], "exposed_ports": [], "running": False}


def _parse_caddy_config(service_name: str, caddy_path: Path) -> list[dict[str, Any]]:
    """Backward-compat wrapper.

    Основная реализация находится в `apps_platform.caddy_parser.parse_caddy_config()`.
    """

    return parse_caddy_config(service_name, caddy_path)


def _expand_env_vars(value: str, *, max_depth: int = 5) -> str:
    """Раскрытие переменных окружения с поддержкой синтаксиса `${VAR:-default}`.

    Поддерживает вложенные выражения в default (например, `${A:-${B:-x}}`) и ограничивает глубину
    рекурсии для защиты от циклов и бесконечной подстановки.
    """

    if not value or not isinstance(value, str):
        return value

    def find_matching_brace(s: str, start: int) -> int | None:
        """Ищет закрывающую `}` для подстроки, начинающейся с `${` в позиции start."""
        i = start
        if not s.startswith("${", i):
            return None
        i += 2
        depth = 1
        while i < len(s):
            if s.startswith("${", i):
                depth += 1
                i += 2
                continue
            if s[i] == "}":
                depth -= 1
                if depth == 0:
                    return i
            i += 1
        return None

    def split_var_default(inner: str) -> tuple[str, str | None]:
        """Разделяет `VAR` и `default` в `VAR:-default`, учитывая вложенные `${...}` в default."""
        i = 0
        depth = 0
        while i < len(inner) - 1:
            if inner.startswith("${", i):
                depth += 1
                i += 2
                continue
            if inner[i] == "}" and depth > 0:
                depth -= 1
                i += 1
                continue
            if depth == 0 and inner.startswith(":-", i):
                return inner[:i], inner[i + 2 :]
            i += 1
        return inner, None

    def expand(s: str, depth: int, seen: set[str]) -> str:
        if depth >= max_depth:
            return s
        if s in seen:
            # Защита от циклов типа VAR=${VAR}
            return s
        seen.add(s)

        out: list[str] = []
        i = 0
        changed = False
        while i < len(s):
            if not s.startswith("${", i):
                out.append(s[i])
                i += 1
                continue

            end = find_matching_brace(s, i)
            if end is None:
                # Некорректная конструкция — оставляем как есть
                out.append(s[i])
                i += 1
                continue

            inner = s[i + 2 : end]
            var_part, default_part = split_var_default(inner)
            var_name = var_part.strip()
            default_raw = default_part if default_part is not None else ""

            replacement = os.environ.get(var_name)
            if replacement is None:
                replacement = expand(default_raw, depth + 1, seen)

            out.append(replacement)
            changed = True
            i = end + 1

        result = "".join(out)
        if not changed:
            return result
        # Разворачиваем значения, которые сами могут содержать `${...}`
        return expand(result, depth + 1, seen)

    return expand(value, 0, set())


_PORT_MAPPING_HOST_CONTAINER_RE = re.compile(r"^(?P<host>\d+):(?P<container>\d+)$")
_PORT_MAPPING_IP_HOST_CONTAINER_RE = re.compile(
    r"^(?P<ip>(?:\[[^\]]+\])|[^:]+):(?P<host>\d+):(?P<container>\d+)$"
)


def _parse_compose_port_mapping(port_mapping: str) -> int | None:
    """Извлекает host_port из записи `ports:` docker-compose.

    Поддерживаемые форматы:
    - `[::1]:8080:80`
    - `0.0.0.0:8080:80`
    - `8080:80`
    - те же варианты с суффиксом протокола (`/tcp`, `/udp`)
    """

    if not port_mapping or not isinstance(port_mapping, str):
        return None

    mapping = port_mapping.strip()
    if "/" in mapping:
        mapping = mapping.split("/", 1)[0].strip()

    m = _PORT_MAPPING_HOST_CONTAINER_RE.fullmatch(mapping)
    if m:
        return int(m.group("host"))

    m = _PORT_MAPPING_IP_HOST_CONTAINER_RE.fullmatch(mapping)
    if m:
        return int(m.group("host"))

    # Fallback: IPv6 без квадратных скобок. Compose обычно ожидает скобки, но на всякий случай
    # поддерживаем формат `::1:8080:80` (делим справа, чтобы не путать двоеточия адреса).
    if ":" in mapping and not mapping.startswith("[") and mapping.count(":") >= 2:
        ip_part, host_port, container_port = mapping.rsplit(":", 2)
        if ip_part and host_port.isdigit() and container_port.isdigit():
            return int(host_port)

    return None


def _get_actual_service_urls(service_name: str, service_path: Path, service_config: dict[str, Any]) -> list[str]:
    """
    Получение действительных URL сервиса из различных источников.

    Приоритет источников:
    1. Caddy конфигурация (реальные домены/пути)
    2. docker-compose.yml (опубликованные порты)
    3. service.yml routing (декларированные маршруты)
    4. Дефолтные значения
    """
    urls: list[str] = []
    seen_urls: set[str] = set()

    def add_url(url: str) -> None:
        if url and url not in seen_urls:
            urls.append(url)
            seen_urls.add(url)

    # 1. Пытаемся получить URL из Caddy конфигурации
    caddy_path = PROJECT_ROOT / "_core" / "caddy"
    if caddy_path.exists():
        caddy_routes = _parse_caddy_config(service_name, caddy_path)
        logger.debug("Caddy routes for %s: %s", service_name, caddy_routes)
        for route in caddy_routes:
            if route.get("type") == "domain":
                domain = route.get("domain", "")
                if domain:
                    add_url(f"https://{domain}")
            elif route.get("type") == "subfolder":
                domain = route.get("domain", "localhost")
                path = route.get("path", f"/{service_name}")
                add_url(f"https://{domain}{path}")

    # 2. Получаем URL из docker-compose.yml (опубликованные порты)
    # TODO(arch): Консолидация источников URL.
    # - Вынести работу с compose/service.yml/Caddyfile в единый модуль (см. TODO в _parse_caddy_config).
    # - Или заменить всё на запрос к master service API.
    compose_file = service_path / "docker-compose.yml"
    if compose_file.exists():
        try:
            with open(compose_file) as f:
                compose_config = yaml.safe_load(f) or {}

            compose_services = compose_config.get("services", {})
            for _svc_name, svc_config in compose_services.items():
                ports = svc_config.get("ports", [])
                for port_mapping in ports:
                    if isinstance(port_mapping, str):
                        # Формат: "host:container" или "ip:host:container" (в т.ч. IPv6 в квадратных скобках)
                        host_port = _parse_compose_port_mapping(port_mapping)
                        if host_port is not None:
                            add_url(f"http://localhost:{host_port}")
                    elif isinstance(port_mapping, int):
                        add_url(f"http://localhost:{port_mapping}")
                    elif isinstance(port_mapping, dict):
                        # Compose spec: { target: 80, published: 8080, protocol: tcp, mode: host }
                        published = port_mapping.get("published")
                        if isinstance(published, int):
                            add_url(f"http://localhost:{published}")
                        elif isinstance(published, str) and published.isdigit():
                            add_url(f"http://localhost:{int(published)}")
        except Exception:
            # Не прерываем выполнение команды list из-за проблем парсинга compose.
            pass

    # 3. Получаем URL из service.yml routing
    routing_configs = service_config.get("routing", [])
    for route in routing_configs:
        route_type = route.get("type", "subfolder")

        if route_type == "domain":
            domain = route.get("domain", "")
            if domain:
                domain = _expand_env_vars(domain)
                add_url(f"https://{domain}")
        elif route_type == "subfolder":
            base_domain = route.get("base_domain", "localhost")
            base_domain = _expand_env_vars(base_domain)
            path = route.get("path", f"/{service_name}")
            add_url(f"https://{base_domain}{path}")
        elif route_type == "port":
            port = route.get("port", route.get("internal_port", 8000))
            add_url(f"http://localhost:{port}")

        # Автоматический поддомен
        if route.get("auto_subdomain", False):
            base = route.get("base_domain", "apps.urfu.online")
            add_url(f"https://{service_name}.{base}")

    # 4. Дефолтный URL если ничего не найдено
    if not urls:
        routing = service_config.get("routing", [])
        if routing:
            # Используем первый маршрут как дефолт
            first_route = routing[0]
            route_type = first_route.get("type", "subfolder")
            if route_type == "domain":
                domain = _expand_env_vars(first_route.get("domain", "localhost"))
                add_url(f"https://{domain}")
            elif route_type == "port":
                port = first_route.get("port", 8000)
                add_url(f"http://localhost:{port}")
            else:
                base_domain = _expand_env_vars(first_route.get("base_domain", "localhost"))
                path = first_route.get("path", f"/{service_name}")
                add_url(f"https://{base_domain}{path}")
        else:
            # Совсем дефолт
            add_url("http://localhost:8000")

    return urls


def get_service_status(service_path: Path) -> str:
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", str(service_path / "docker-compose.yml"), "ps", "-q"],
            capture_output=True, text=True, cwd=service_path, timeout=DOCKER_TIMEOUT
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


@app.command("list")
def list_services(
    visibility: str | None = typer.Option(None, "--visibility", "-v", help="Фильтр по видимости (public/internal)"),
    status_filter: str | None = typer.Option(None, "--status", "-s", help="Фильтр по статусу (running/stopped)"),
    check_availability: bool = typer.Option(False, "--check", "-c", help="Проверять доступность сервисов"),
    insecure: bool = typer.Option(
        False,
        "--insecure",
        help="Отключить проверку SSL сертификата при проверке доступности (также можно PLATFORM_SSL_VERIFY=false)",
    ),
) -> None:
    """Показать все сервисы."""
    services = get_services()
    container_map = _get_all_container_statuses()  # Один запрос вместо N

    ssl_verify = _get_ssl_verify(insecure=insecure)

    table = Table(title="Сервисы платформы")
    table.add_column("Service", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("URL / Path", style="blue")
    table.add_column("Status", style="yellow")
    table.add_column("Available", style="green")

    for name, info in sorted(services.items()):
        if visibility and info["type"] != visibility:
            continue

        # Быстрая проверка статуса через кэш контейнеров
        svc_status = "stopped"
        matching = [c for c in container_map if _matches_service(c, name)]
        if matching:
            # Берём статус первого совпавшего контейнера
            first_status = container_map[matching[0]].split()[0].lower()
            if first_status in ("up", "running", "restarting", "healthy"):
                svc_status = f"running ({len(matching)})"

        if status_filter:
            if status_filter == "running" and "running" not in svc_status:
                continue
            if status_filter == "stopped" and "running" in svc_status:
                continue

        # Получаем информацию о маршрутизации из service.yml
        service_path = info["path"]
        service_yml_path = service_path / "service.yml"

        # Загружаем service.yml конфигурацию
        service_config = {}
        if service_yml_path.exists():
            with open(service_yml_path) as f:
                try:
                    service_config = yaml.safe_load(f) or {}
                except Exception:
                    console.print(f"[yellow]⚠️  Не удалось прочитать service.yml для '{name}'[/yellow]")

        # Получаем действительные URL сервиса из всех источников
        urls = _get_actual_service_urls(name, service_path, service_config)

        # Форматируем URLs для отображения
        # Показываем максимум MAX_URLS_DISPLAY URL
        url_display = "\n".join(urls[:MAX_URLS_DISPLAY])
        if len(urls) > MAX_URLS_DISPLAY:
            url_display += f"\n... +{len(urls) - MAX_URLS_DISPLAY} ещё"

        # Проверка доступности - проверяем каждый URL пока не найдём рабочий
        availability_status = "—"
        if check_availability and "running" in svc_status:
            checked_urls = []
            for url in urls:
                # Пропускаем URL с переменными которые не раскрылись
                if '${' in url or '$PLATFORM_DOMAIN' in url:
                    continue
                checked_urls.append(url)
                try:
                    response = requests.get(url, timeout=AVAILABILITY_TIMEOUT, verify=ssl_verify)
                    if response.status_code < 500:
                        availability_status = "✓"
                        break
                    else:
                        availability_status = f"✗ {response.status_code}"
                except requests.exceptions.ConnectionError:
                    availability_status = "✗ conn"
                except requests.exceptions.Timeout:
                    availability_status = "✗ timeout"
                except Exception as e:
                    availability_status = f"✗ {type(e).__name__}"

            # Если все проверки не прошли, но сервис running - ставим статус
            if availability_status.startswith("✗") and len(checked_urls) > 0:
                pass  # Оставляем последнюю ошибку
            elif not checked_urls and "running" in svc_status:
                availability_status = "?"  # Не смогли проверить
        elif "running" in svc_status:
            availability_status = "?"  # Сервис запущен, но проверка не включена

        status_style = "green" if "running" in svc_status else "red"
        avail_style = (
            "green"
            if availability_status == "✓"
            else ("red" if availability_status.startswith("✗") else "white")
        )
        table.add_row(
            name,
            info["type"],
            url_display,
            f"[{status_style}]{svc_status}[/{status_style}]",
            f"[{avail_style}]{availability_status}[/{avail_style}]"
        )

    console.print(table)


@app.command()
def new(
    name: str = typer.Argument(..., help="Имя сервиса"),
    visibility: str = typer.Argument("public", help="Видимость сервиса (public/internal)"),
) -> None:
    """Создать новый сервис из шаблона."""
    validate_service_name(name)
    if visibility not in ("public", "internal"):
        console.print("[red]❌ visibility должен быть 'public' или 'internal'[/red]")
        raise typer.Exit(1)

    config = get_config()
    services_path = PROJECT_ROOT / config.get("services_path", "services") / visibility
    service_dir = services_path / name

    if service_dir.exists():
        console.print(f"[red]❌ Сервис '{name}' уже существует[/red]")
        raise typer.Exit(1)

    service_dir.mkdir(parents=True, exist_ok=True)

    service_yml = {
        "name": name,
        "display_name": name.replace("-", " ").title(),
        "version": "1.0.0",
        "description": f"Сервис {name}",
        "maintainer": "team@example.com",
        "type": "docker-compose",
        "visibility": visibility,
        "routing": [{
            "type": "subfolder",
            "base_domain": "apps.example.com",
            "path": f"/{name}",
            "strip_prefix": True,
            "internal_port": 8000,
        }],
        "health": {"enabled": True, "endpoint": "/healthz", "interval": "30s"},
        "backup": {"enabled": False, "schedule": "0 2 * * *", "retention": 7},
    }

    with open(service_dir / "service.yml", "w") as f:
        yaml.dump(service_yml, f, default_flow_style=False, allow_unicode=True)

    docker_compose = f"""version: "3.8"
services:
  {name.replace('-', '_')}:
    build: .
    container_name: {name}
    restart: unless-stopped
    ports:
      - "8000:8000"
    networks:
      - servicenet
      - platform
    environment:
      - ENV=production
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
      interval: 30s
      timeout: 10s
      retries: 3
networks:
  servicenet:
    name: {name}_network
  platform:
    external: true
    name: platform_network
"""
    with open(service_dir / "docker-compose.yml", "w") as f:
        f.write(docker_compose)

    with open(service_dir / ".env.example", "w") as f:
        f.write("# Переменные окружения сервиса\nENV=production\nDATABASE_URL=postgresql://user:pass@db:5432/dbname\n")

    with open(service_dir / ".env", "w") as f:
        f.write("# Переменные окружения — скопируйте из .env.example и заполните\n")

    readme = f"""# {name.replace("-", " ").title()}
Описание
{service_yml['description']}
Запуск
platform deploy {name}
Логи
platform logs {name}
"""
    with open(service_dir / "README.md", "w") as f:
        f.write(readme)

    (service_dir / "src").mkdir(exist_ok=True)
    (service_dir / "src" / "__init__.py").touch()

    console.print(f"[green]✅ Сервис '{name}' создан в {service_dir}[/green]")
    console.print("\nСледующие шаги:")
    console.print(f"  1. Отредактируйте [cyan]{service_dir}/service.yml[/cyan]")
    console.print(f"  2. Добавьте код приложения в [cyan]{service_dir}/src/[/cyan]")
    console.print(f"  3. Задеплойте: [cyan]platform deploy {name}[/cyan]")


@app.command()
def deploy(
    service: str = typer.Argument(..., help="Имя сервиса"),
    build: bool = typer.Option(False, "--build", "-b", help="Пересобрать образы"),
    pull: bool = typer.Option(False, "--pull", "-p", help="Обновить образы"),
) -> None:
    """Задеплоить сервис."""
    service_path = get_service_or_fail(get_services(), service)

    args = ["up", "-d"]
    if build:
        args.append("--build")
    if pull:
        args.append("--pull")

    console.print(f"[blue]ℹ️  Деплой сервиса '{service}'...[/blue]")
    result = compose_cmd(service_path, *args)

    if result.returncode == 0:
        console.print(f"[green]✅ Сервис '{service}' успешно задеплоен[/green]")
    else:
        console.print(f"[red]❌ Ошибка деплоя сервиса '{service}'[/red]")
        raise typer.Exit(1)


@app.command()
def stop(service: str = typer.Argument(..., help="Имя сервиса")) -> None:
    """Остановить сервис."""
    service_path = get_service_or_fail(get_services(), service)

    console.print(f"[blue]ℹ️  Остановка сервиса '{service}'...[/blue]")
    result = compose_cmd(service_path, "down")

    if result.returncode == 0:
        console.print(f"[green]✅ Сервис '{service}' остановлен[/green]")
    else:
        console.print(f"[red]❌ Ошибка остановки сервиса '{service}'[/red]")
        raise typer.Exit(1)


@app.command()
def restart(service: str = typer.Argument(..., help="Имя сервиса")) -> None:
    """Перезапустить сервис."""
    service_path = get_service_or_fail(get_services(), service)

    console.print(f"[blue]ℹ️  Перезапуск сервиса '{service}'...[/blue]")
    compose_cmd(service_path, "restart")
    console.print(f"[green]✅ Сервис '{service}' перезапущен[/green]")


@app.command()
def status(service: str | None = typer.Argument(None, help="Имя сервиса (опционально)")) -> None:
    """Показать статус сервисов."""
    if service:
        service_path = get_service_or_fail(get_services(), service)
        status = get_service_status(service_path)

        console.print(f"\n[bold]Сервис:[/bold] {service}")
        console.print(f"[bold]Путь:[/bold] {service_path}")
        console.print(f"[bold]Статус:[/bold] {status}")

        try:
            with docker_client() as client:
                containers = client.containers.list(filters={"name": service})
                if containers:
                    container = containers[0]
                    stats = container.stats(stream=False)
                    if "memory_stats" in stats:
                        memory = stats["memory_stats"]
                        if "usage" in memory and "limit" in memory:
                            memory_mb = memory["usage"] / (1024 * 1024)
                            memory_limit_mb = memory["limit"] / (1024 * 1024)
                            console.print(f"[bold]Память:[/bold] {memory_mb:.1f}MB / {memory_limit_mb:.1f}MB")
        except Exception:
            # Память — дополнительная информация, не должна ломать команду.
            pass
    else:
        list_services()


@app.command()
def logs(
    service: str = typer.Argument(..., help="Имя сервиса"),
    lines: int = typer.Option(100, "--lines", "-n", help="Количество строк"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Следить за логами"),
) -> None:
    """Просмотр логов сервиса."""
    service_path = get_service_or_fail(get_services(), service)

    args = ["logs", f"--tail={lines}"]
    if follow:
        args.append("-f")

    compose_cmd(service_path, *args)


@app.command()
def backup(service: str = typer.Argument(..., help="Имя сервиса")) -> None:
    """Создать бэкап сервиса."""
    service_path = get_service_or_fail(get_services(), service)
    service_yml_path = service_path / "service.yml"

    if not service_yml_path.exists():
        console.print("[red]❌ Файл service.yml не найден[/red]")
        raise typer.Exit(1)

    with open(service_yml_path) as f:
        service_config = yaml.safe_load(f)

    backup_config = service_config.get("backup", {})
    if not backup_config.get("enabled", False):
        console.print("[yellow]⚠️  Бэкапы не включены в service.yml[/yellow]")
        raise typer.Exit(1)

    config = get_config()
    master_url = config.get("master_url", "http://localhost:8001")

    try:
        response = requests.post(
            f"{master_url}/api/backups/service/{service}/backup",
            json={"reason": "manual"},
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code == 200:
            result = response.json()
            console.print(f"[green]✅ Бэкап создан: {result.get('name', 'N/A')}[/green]")
        else:
            console.print(f"[red]❌ API вернул статус {response.status_code}[/red]")
            raise typer.Exit(1)
    except requests.exceptions.ConnectionError as e:
        console.print("[red]❌ Master Service недоступен. Запустите бэкап вручную через restic.[/red]")
        raise typer.Exit(1) from e
    except Exception as e:
        console.print(f"[red]❌ Ошибка: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def info() -> None:
    """Показать информацию о платформе."""
    config = get_config()
    console.print("\n[bold blue]Platform Master Service[/bold blue]\n")
    console.print(f"[bold]Project Root:[/bold] {PROJECT_ROOT}")
    console.print(f"[bold]Environment:[/bold] {config.get('environment', 'unknown')}")
    console.print(f"[bold]Core Path:[/bold] {config.get('core_path', '_core')}")
    console.print(f"[bold]Services Path:[/bold] {config.get('services_path', 'services')}")

    services = get_services()
    core_count = sum(1 for s in services.values() if s["type"] == "core")
    public_count = sum(1 for s in services.values() if s["type"] == "public")
    internal_count = sum(1 for s in services.values() if s["type"] == "internal")

    console.print(f"\n[bold]Всего сервисов:[/bold] {len(services)}")
    console.print(f"  - Core: {core_count}")
    console.print(f"  - Public: {public_count}")
    console.print(f"  - Internal: {internal_count}")


@app.command()
def reload(
    container: str = typer.Option(CADDY_DEFAULT_CONTAINER_NAME, "--container", "-c", help="Имя контейнера Caddy"),
) -> None:
    """Перезагрузить конфигурацию Caddy."""
    # Валидация имени контейнера
    if not container or not container.replace("-", "").replace("_", "").isalnum():
        console.print("[red]❌ Неверное имя контейнера[/red]")
        raise typer.Exit(1)

    # Проверка существования контейнера
    try:
        check_result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, check=True
        )
        running_containers = check_result.stdout.strip().split("\n")
        if container not in running_containers:
            console.print(f"[red]❌ Контейнер '{container}' не найден или не запущен[/red]")
            console.print("[yellow]Доступные контейнеры:[/yellow]")
            for c in running_containers:
                if c:
                    console.print(f"  - {c}")
            raise typer.Exit(1)
    except subprocess.CalledProcessError as e:
        console.print("[red]❌ Ошибка проверки контейнеров Docker[/red]")
        raise typer.Exit(1) from e

    console.print(f"[blue]ℹ️  Перезагрузка Caddy в контейнере '{container}'...[/blue]")
    try:
        subprocess.run(
            ["docker", "exec", container, "caddy", "reload", "--config", "/etc/caddy/Caddyfile"],
            capture_output=True, text=True, check=True
        )
        console.print("[green]✅ Caddy перезапущен[/green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]❌ Ошибка: {e.stderr.strip()}[/red]")
        raise typer.Exit(1) from e
    except Exception:
        logger.exception("Unhandled error while reloading Caddy")
        console.print("[red]❌ Неизвестная ошибка при перезагрузке Caddy[/red]")
        raise typer.Exit(1) from None


def main() -> None:
    """Точка входа CLI."""
    app()


if __name__ == "__main__":
    main()
