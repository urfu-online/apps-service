#!/usr/bin/env python3
"""Аудит сервисов платформы: манифесты, контейнеры, сети.

Статический + runtime-аудит services/{public,internal}/*:
  - visibility ↔ директория (public/internal)
  - наличие routing и container_name, корректность internal_port
  - запущенность и health контейнеров из routing
  - объявление platform_network (external) в docker-compose.yml
  - членство контейнера в platform_network

ТОЛЬКО ЧТЕНИЕ. Выводит таблицу с ошибками и готовые команды исправления.

ЗАПУСК:
  python3 scripts/validate.py                 # /apps/services (или SERVICES_ROOT)
  SERVICES_ROOT=/apps/services python3 scripts/validate.py

ЗАВИСИМОСТИ: pyyaml, rich  (pip install pyyaml rich)
"""
import os
import subprocess
import sys
from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
BASE_DIR = Path(os.environ.get("SERVICES_ROOT", "/apps/services"))
PLATFORM_NET = "platform_network"


def run(cmd: str) -> str:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()


def get_running_containers() -> dict:
    """{container_name: (status, ports_str)} — только запущенные."""
    out = run("docker ps --format '{{.Names}}|{{.Status}}|{{.Ports}}'")
    result = {}
    for row in out.splitlines():
        parts = row.split("|", 2)
        if len(parts) >= 2:
            result[parts[0]] = (parts[1], parts[2] if len(parts) > 2 else "")
    return result


def get_container_networks() -> dict:
    """{container_name: [network_names]}"""
    out = run(
        "docker inspect -f '{{.Name}} {{range $k, $v := .NetworkSettings.Networks}}"
        "{{$k}} {{end}}' $(docker ps -q)"
    )
    nets = {}
    for line in out.splitlines():
        parts = line.strip("/").split()
        if len(parts) >= 2:
            nets[parts[0]] = parts[1:]
    return nets


def validate_service(svc_dir: Path, containers: dict, nets: dict) -> dict:
    res = {
        "name": svc_dir.name,
        "dir": str(svc_dir.relative_to(BASE_DIR)),
        "settings": {},
        "notes": [],
        "errors": [],
        "fixes": [],
    }
    yml_file = svc_dir / "service.yml"
    compose_file = svc_dir / "docker-compose.yml"

    if not yml_file.exists():
        res["errors"].append("Отсутствует service.yml")
        return res

    try:
        manifest = yaml.safe_load(yml_file.read_text())
    except yaml.YAMLError as e:
        res["errors"].append(f"YAML syntax: {str(e)[:80]}")
        return res

    visibility = manifest.get("visibility", "internal")
    routing = manifest.get("routing", None)

    # 1. Visibility ↔ директория
    expected_dir = "public" if visibility == "public" else "internal"
    if svc_dir.parent.name != expected_dir:
        res["errors"].append(f"visibility={visibility}, но лежит в {svc_dir.parent.name}/")
        res["fixes"].append(
            f"mkdir -p services/{expected_dir} && mv {svc_dir} services/{expected_dir}/"
        )

    # 2. Routing: сервисы БЕЗ секции routing (порт/TCP, например imap-proxy)
    #    — это нормальный режим, не ошибка.
    if routing is None:
        res["notes"].append("нет секции routing — порт/TCP-сервис (HTTP-роутинга нет)")
        routing = []
    elif not routing:
        res["errors"].append("routing: [] — секция пуста")

    res["settings"] = {
        "type": manifest.get("type", "docker-compose"),
        "vis": visibility,
        "routes": len(routing),
        "containers": [r.get("container_name") for r in routing if r.get("container_name")],
    }

    checked_containers = set()
    for i, rule in enumerate(routing):
        cname = rule.get("container_name")
        iport = rule.get("internal_port")

        if not cname:
            res["errors"].append(f"routing[{i}]: нет container_name (без него Caddy проксирует на host.docker.internal — legacy)")
            res["fixes"].append(f"Добавить container_name в routing[{i}] service.yml")
        else:
            checked_containers.add(cname)

        if iport is not None and not str(iport).isdigit():
            res["errors"].append(f"routing[{i}]: internal_port='{iport}' не число")

        if cname and cname not in containers:
            res["errors"].append(f"контейнер '{cname}' не запущен")
            res["fixes"].append(f"cd {svc_dir} && docker compose up -d   # или: platform deploy {res['name']}")
        elif cname:
            status = containers.get(cname, ("", ""))[0]
            if "unhealthy" in status.lower():
                res["errors"].append(f"контейнер '{cname}' unhealthy ({status})")

    # 3. docker-compose: объявление platform_network
    if compose_file.exists():
        try:
            compose = yaml.safe_load(compose_file.read_text()) or {}
            networks = compose.get("networks", {}) or {}
            net_decl = networks.get(PLATFORM_NET, {}) or {}
            if not (PLATFORM_NET in networks and net_decl.get("external")):
                res["errors"].append(f"в docker-compose.yml нет 'networks: {PLATFORM_NET}: external: true'")
                res["fixes"].append(
                    f"networks:\n  {PLATFORM_NET}:\n    external: true\n    name: {PLATFORM_NET}"
                )
        except Exception:
            res["errors"].append("docker-compose.yml невалиден (YAML)")
    elif routing:
        res["notes"].append("нет docker-compose.yml")

    # 4. Членство контейнера в platform_network (по всем контейнерам из routing)
    for cname in checked_containers:
        svc_nets = nets.get(cname, [])
        if svc_nets and PLATFORM_NET not in svc_nets:
            res["errors"].append(f"контейнер '{cname}' не в {PLATFORM_NET} (сети: {' '.join(svc_nets)})")
            res["fixes"].append(f"docker network connect {PLATFORM_NET} {cname}")

    return res


def main() -> int:
    if not BASE_DIR.exists():
        console.print(f"[red]Не найден каталог сервисов: {BASE_DIR}[/red]")
        return 2

    containers = get_running_containers()
    nets = get_container_networks()

    table = Table(title="Аудит сервисов", show_header=True, header_style="bold magenta")
    table.add_column("Сервис / Путь")
    table.add_column("Настройки")
    table.add_column("Ошибки")
    table.add_column("Фикс")

    fixes_script = []
    total_errors = 0

    for d_type in ["public", "internal"]:
        d_path = BASE_DIR / d_type
        if not d_path.exists():
            continue
        for svc_dir in sorted(d_path.iterdir()):
            if not svc_dir.is_dir():
                continue
            res = validate_service(svc_dir, containers, nets)
            total_errors += len(res["errors"])

            settings_str = (
                f"type:{res['settings'].get('type')} vis:{res['settings'].get('vis')} "
                f"routes:{res['settings'].get('routes')}"
            )
            if res["notes"]:
                settings_str += "\n[dim]" + "; ".join(res["notes"]) + "[/dim]"
            errors_str = "\n".join(res["errors"])
            fixes_str = "\n".join(res["fixes"]) or "—"

            table.add_row(
                f"[bold]{res['name']}[/]\n[dim]{res['dir']}[/dim]",
                settings_str,
                f"[red]{errors_str}[/red]" if res["errors"] else "[green]OK[/green]",
                f"[yellow]{fixes_str}[/yellow]" if res["fixes"] else "",
            )
            fixes_script.extend(res["fixes"])

    console.print(table)

    if fixes_script:
        console.print(
            Panel("\n;\n".join(fixes_script), title="Готовые команды для исправления", border_style="yellow")
        )
    else:
        console.print("[green]Ошибок не найдено.[/green]")

    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
