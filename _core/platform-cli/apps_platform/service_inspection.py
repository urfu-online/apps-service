"""Сервисные утилиты, извлечённые из ``cli.py`` при рефакторинге Шага 8.

Здесь живут функции, которые:
- формально не перечислены в перечне утилит, оставленных в ``cli.py``
  (т.е. не ``_deep_merge`` / ``get_project_root`` / ``get_config`` /
  ``_parse_bool_env`` / ``_get_ssl_verify`` / ``docker_client`` / ``compose_cmd``
  / парсеры ``_parse_caddy_config`` и ``_parse_compose_port_mapping``);
- не являются сами по себе командами CLI, а обслуживают команды из
  ``apps_platform.commands`` (особенно ``list_services``).

Чтобы тесты с патчами вида ``apps_platform.cli._matches_service`` продолжали
работать, в ``cli.py`` эти имена ре-экспортируются.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from apps_platform.caddy_parser import parse_caddy_config

logger = logging.getLogger(__name__)

DOCKER_TIMEOUT = 10


def _get_all_container_statuses() -> dict[str, str]:
    """Один запрос к Docker для получения статусов всех контейнеров."""
    try:
        res = subprocess.run(
            ["docker", "ps", "-a", "--format", "json"],
            capture_output=True,
            text=True,
            check=True,
            timeout=DOCKER_TIMEOUT,
        )
        statuses: dict[str, str] = {}
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
    if container_name == service_name:
        return True
    if container_name.startswith((f"{service_name}-", f"{service_name}_")):
        return True
    if container_name.endswith((f"-{service_name}", f"_{service_name}")):
        return True
    return service_name in container_name


def _get_container_network_info(container_name: str, *, docker_client_factory: Any) -> dict[str, Any]:
    """Получение информации о сети контейнера (IP, порты).

    ``docker_client_factory`` инжектируется вызывающей стороной, чтобы избежать
    циклической зависимости ``service_inspection`` → ``cli`` → ``service_inspection``.
    """
    try:
        with docker_client_factory() as client:
            container = client.containers.get(container_name)
            network_settings = container.attrs.get("NetworkSettings", {})
            is_running = container.status == "running"

        networks = network_settings.get("Networks", {})
        ip_addresses = [
            {"network": net_name, "ip": net_config["IPAddress"]}
            for net_name, net_config in networks.items()
            if net_config.get("IPAddress")
        ]

        ports = network_settings.get("Ports", {})
        exposed_ports = []
        for port_key, port_bindings in ports.items():
            if not port_bindings:
                continue
            for binding in port_bindings:
                exposed_ports.append(
                    {
                        "container_port": port_key,
                        "host_ip": binding.get("HostIp", "0.0.0.0"),
                        "host_port": binding.get("HostPort"),
                    }
                )

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
    """Backward-compat wrapper над ``apps_platform.caddy_parser.parse_caddy_config``."""
    return parse_caddy_config(service_name, caddy_path)


def _expand_env_vars(value: str, *, max_depth: int = 5) -> str:
    """Раскрытие ``${VAR}`` / ``${VAR:-default}`` с защитой от циклов и вложенности."""
    if not value or not isinstance(value, str):
        return value

    def find_matching_brace(s: str, start: int) -> int | None:
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
            return s
        seen = seen | {s}

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
        return expand(result, depth + 1, seen)

    return expand(value, 0, set())


_PORT_MAPPING_HOST_CONTAINER_RE = re.compile(r"^(?P<host>\d+):(?P<container>\d+)$")
_PORT_MAPPING_IP_HOST_CONTAINER_RE = re.compile(
    r"^(?P<ip>(?:\[[^\]]+\])|[^:]+):(?P<host>\d+):(?P<container>\d+)$"
)


def _parse_compose_port_mapping(port_mapping: str) -> int | None:
    """Извлекает host_port из записи ``ports:`` docker-compose.

    Поддерживает ``[::1]:8080:80``, ``0.0.0.0:8080:80``, ``8080:80`` и те же
    варианты с суффиксом протокола ``/tcp`` / ``/udp``.
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

    if ":" in mapping and not mapping.startswith("[") and mapping.count(":") >= 2:
        ip_part, host_port, container_port = mapping.rsplit(":", 2)
        if ip_part and host_port.isdigit() and container_port.isdigit():
            return int(host_port)

    return None


def _get_actual_service_urls(
    service_name: str,
    service_path: Path,
    service_config: dict[str, Any],
    *,
    project_root: Path,
) -> list[str]:
    """Получение URL сервиса из Caddy / docker-compose / service.yml routing.

    ``project_root`` инжектируется вызывающей стороной, чтобы избежать
    циклической зависимости от ``apps_platform.cli.get_project_root``.
    """
    import yaml

    urls: list[str] = []
    seen_urls: set[str] = set()

    def add_url(url: str) -> None:
        if url and url not in seen_urls:
            urls.append(url)
            seen_urls.add(url)

    caddy_path = project_root / "_core" / "caddy"
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

    compose_file = service_path / "docker-compose.yml"
    if compose_file.exists():
        try:
            with open(compose_file) as f:
                compose_config = yaml.safe_load(f) or {}

            for svc_config in compose_config.get("services", {}).values():
                for port_mapping in svc_config.get("ports", []):
                    if isinstance(port_mapping, str):
                        host_port = _parse_compose_port_mapping(port_mapping)
                        if host_port is not None:
                            add_url(f"http://localhost:{host_port}")
                    elif isinstance(port_mapping, int):
                        add_url(f"http://localhost:{port_mapping}")
                    elif isinstance(port_mapping, dict):
                        published = port_mapping.get("published")
                        if isinstance(published, int):
                            add_url(f"http://localhost:{published}")
                        elif isinstance(published, str) and published.isdigit():
                            add_url(f"http://localhost:{int(published)}")
        except Exception as exc:
            logger.debug("compose ports parse skipped: %s", exc)

    for route in service_config.get("routing", []):
        route_type = route.get("type", "subfolder")

        if route_type == "domain":
            domain = route.get("domain", "")
            if domain:
                domain = _expand_env_vars(domain)
                add_url(f"https://{domain}")
        elif route_type == "subfolder":
            base_domain = _expand_env_vars(route.get("base_domain", "localhost"))
            path = route.get("path", f"/{service_name}")
            add_url(f"https://{base_domain}{path}")
        elif route_type == "port":
            port = route.get("port", route.get("internal_port", 8000))
            add_url(f"http://localhost:{port}")

        if route.get("auto_subdomain", False):
            base = route.get("base_domain", "apps.urfu.online")
            add_url(f"https://{service_name}.{base}")

    if not urls:
        routing = service_config.get("routing", [])
        if routing:
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
            add_url("http://localhost:8000")

    return urls
