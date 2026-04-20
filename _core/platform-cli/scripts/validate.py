#!/usr/bin/env python3
import yaml, subprocess, json, os, sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()
BASE_DIR = Path("/apps/services")
PLATFORM_NET = "platform_network"

def run(cmd: str) -> str:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()

def get_running_containers() -> dict:
    """{container_name: (status, ports_str)}"""
    out = run("docker ps --format '{{.Names}}:{{.Status}}:{{.Ports}}'")
    return {row.split(":")[0]: row.split(":")[1:] for row in out.splitlines() if ":" in row}

def get_container_networks() -> dict:
    """{container_name: [network_names]}"""
    out = run("docker inspect -f '{{.Name}} {{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' $(docker ps -q)")
    nets = {}
    for line in out.splitlines():
        parts = line.strip("/").split()
        if len(parts) >= 2:
            nets[parts[0]] = parts[1:]
    return nets

def validate_service(svc_dir: Path, containers: dict, nets: dict) -> dict:
    svc_name = svc_dir.name
    yml_file = svc_dir / "service.yml"
    compose_file = svc_dir / "docker-compose.yml"
    
    res = {"name": svc_name, "dir": str(svc_dir.relative_to(BASE_DIR)), "settings": {}, "errors": [], "fixes": []}
    
    if not yml_file.exists():
        res["errors"].append("Отсутствует service.yml")
        return res
        
    try:
        manifest = yaml.safe_load(yml_file.read_text())
    except yaml.YAMLError as e:
        res["errors"].append(f"YAML syntax: {str(e)[:60]}")
        return res

    visibility = manifest.get("visibility", "internal")
    routing = manifest.get("routing", [])
    
    res["settings"] = {
        "type": manifest.get("type", "docker-compose"),
        "vis": visibility,
        "routes": len(routing),
        "containers": [r.get("container_name") for r in routing if r.get("container_name")]
    }

    # 1. Visibility vs Directory
    expected_dir = "public" if visibility == "public" else "internal"
    if svc_dir.parent.name != expected_dir:
        res["errors"].append(f"visibility={visibility}, но лежит в {svc_dir.parent.name}")
        res["fixes"].append(f"mkdir -p services/{expected_dir} && mv {svc_dir} services/{expected_dir}/")

    # 2. Routing checks
    if not routing:
        res["errors"].append("Нет маршрутизации (routing пуст)")
        
    for i, rule in enumerate(routing):
        cname = rule.get("container_name")
        iport = rule.get("internal_port")
        
        if not cname:
            res["errors"].append(f"routing[{i}]: нет container_name")
            res["fixes"].append(f"Добавь 'container_name: <имя>' в routing[{i}]")
            
        if iport and not str(iport).isdigit():
            res["errors"].append(f"routing[{i}]: internal_port='{iport}' не число")

        # Check if container matches running state
        if cname and cname not in containers:
            res["errors"].append(f"container '{cname}' не запущен")
            res["fixes"].append(f"cd {svc_dir} && docker compose up -d")
        elif cname:
            status = containers.get(cname, [""])[0]
            if "unhealthy" in status.lower():
                res["errors"].append(f"container '{cname}' unhealthy")
                
    # 3. Docker compose & network
    if compose_file.exists():
        try:
            compose = yaml.safe_load(compose_file.read_text())
            services = compose.get("services", {})
            networks = compose.get("networks", {})
            
            has_platform = PLATFORM_NET in networks and networks.get(PLATFORM_NET, {}).get("external")
            if not has_platform:
                res["errors"].append("Нет 'platform_network: external: true' в networks")
                res["fixes"].append(f"Добавь в docker-compose.yml:\nnetworks:\n  {PLATFORM_NET}:\n    external: true\n    name: {PLATFORM_NET}")
        except Exception:
            res["errors"].append("docker-compose.yml невалиден")
            
    # 4. Network membership check
    if cname := res["settings"]["containers"] and res["settings"]["containers"][0]:
        svc_nets = nets.get(cname, [])
        if PLATFORM_NET not in svc_nets:
            res["errors"].append(f"container '{cname}' не в {PLATFORM_NET}")
            res["fixes"].append(f"docker network connect {PLATFORM_NET} {cname}")
            
    return res

def main():
    containers = get_running_containers()
    nets = get_container_networks()
    
    table = Table(title="🔍 Аудит сервисов", show_header=True, header_style="bold magenta")
    table.add_column("Сервис / Путь")
    table.add_column("Настройки")
    table.add_column("Ошибки")
    table.add_column("Фикс")
    
    fixes_script = []
    
    for d_type in ["public", "internal"]:
        d_path = BASE_DIR / d_type
        if not d_path.exists(): continue
        for svc_dir in sorted(d_path.iterdir()):
            if not svc_dir.is_dir(): continue
            res = validate_service(svc_dir, containers, nets)
            
            settings_str = f"type:{res['settings'].get('type')} vis:{res['settings'].get('vis')} routes:{res['settings'].get('routes')}"
            errors_str = "\n".join(res["errors"]) or "✅ Нет"
            fixes_str = "\n".join(res["fixes"]) or "—"
            
            table.add_row(
                f"[bold]{res['name']}[/]\n[dim]{res['dir']}[/dim]",
                settings_str,
                f"[red]{errors_str}[/red]" if res["errors"] else "[green]✅[/green]",
                f"[yellow]{fixes_str}[/yellow]" if fixes_str else ""
            )
            
            fixes_script.extend(res["fixes"])
            
    console.print(table)
    
    if fixes_script:
        console.print(Panel(
            ";\n".join(fixes_script),
            title="🛠 Готовые команды для исправления",
            border_style="yellow"
        ))

if __name__ == "__main__":
    main()
