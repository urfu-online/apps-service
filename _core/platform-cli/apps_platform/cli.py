"""
CLI утилита для управления платформой Platform Master Service
"""

import subprocess
import sys
from pathlib import Path
from typing import Optional

import docker
import requests
import typer
import yaml
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="platform",
    help="CLI утилита для управления платформой Platform Master Service",
    add_completion=False,
)
console = Console()

# Глобальные переменные для конфигурации
PROJECT_ROOT: Optional[Path] = None
CONFIG_FILE: Optional[Path] = None


def get_config() -> dict:
    """Загрузка конфигурации из .ops-config.yml с поддержкой local override"""
    global PROJECT_ROOT, CONFIG_FILE

    config_candidates = [
        Path.cwd() / ".ops-config.yml",
        Path(__file__).parent.parent / ".ops-config.yml",
        Path.home() / ".config" / "ops-manager" / "config.yml",
    ]

    for cfg_path in config_candidates:
        if cfg_path.exists():
            CONFIG_FILE = cfg_path
            with open(cfg_path) as f:
                config = yaml.safe_load(f)

            # Применяем local override если существует
            local_override = cfg_path.parent / ".ops-config.local.yml"
            if local_override.exists():
                with open(local_override) as f:
                    local_data = yaml.safe_load(f)
                if local_data and isinstance(local_data, dict):
                    config.update(local_data)

            PROJECT_ROOT = Path(config.get("project_root", "/apps"))
            return config
    
    console.print("[red]❌ Конфигурационный файл не найден. Запустите ./install.sh[/red]")
    sys.exit(1)


def get_services() -> dict:
    """Сканирование сервисов в проекте"""
    config = get_config()
    services = {}
    
    core_path = PROJECT_ROOT / config.get("core_path", "_core")
    services_path = PROJECT_ROOT / config.get("services_path", "services")
    
    # Сканирование core сервисов
    if core_path.exists():
        for svc_dir in core_path.iterdir():
            if svc_dir.is_dir() and (svc_dir / "docker-compose.yml").exists():
                services[svc_dir.name] = {
                    "path": svc_dir,
                    "type": "core",
                }
    
    # Сканирование public/internal сервисов
    for subdir in ["public", "internal"]:
        type_dir = services_path / subdir
        if type_dir.exists():
            for svc_dir in type_dir.iterdir():
                if svc_dir.is_dir() and (svc_dir / "docker-compose.yml").exists():
                    services[svc_dir.name] = {
                        "path": svc_dir,
                        "type": subdir,
                    }
    
    return services


def compose_cmd(service_path: Path, *args: str) -> subprocess.CompletedProcess:
    """Выполнение команды docker compose"""
    compose_file = service_path / "docker-compose.yml"
    cmd = ["docker", "compose", "--project-directory", str(service_path), "-f", str(compose_file), *args]
    return subprocess.run(cmd, capture_output=False)


def get_service_status(service_path: Path) -> str:
    """Получение статуса сервиса"""
    try:
        result = subprocess.run(
            ["docker", "compose", "--project-directory", str(service_path), "-f", str(service_path / "docker-compose.yml"), "ps", "-q"],
            capture_output=True,
            text=True
        )
        containers = [c for c in result.stdout.strip().split("\n") if c]
        if len(containers) == 0:
            return "stopped"
        return f"running ({len(containers)})"
    except Exception:
        return "error"


@app.command()
def list(
    visibility: Optional[str] = typer.Option(None, "--visibility", "-v", help="Фильтр по видимости (public/internal)"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Фильтр по статусу (running/stopped)"),
):
    """Показать все сервисы"""
    services = get_services()
    
    table = Table(title="Сервисы платформы")
    table.add_column("Service", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Path", style="green")
    table.add_column("Status", style="yellow")
    
    for name, info in sorted(services.items()):
        # Фильтрация по visibility
        if visibility and info["type"] != visibility:
            continue
        
        # Фильтрация по status
        svc_status = get_service_status(info["path"])
        if status:
            if status == "running" and not svc_status.startswith("running"):
                continue
            if status == "stopped" and svc_status != "stopped":
                continue
        
        short_path = str(info["path"].relative_to(PROJECT_ROOT))
        status_style = "green" if svc_status.startswith("running") else "red"
        
        table.add_row(
            name,
            info["type"],
            short_path,
            f"[{status_style}]{svc_status}[/{status_style}]",
        )
    
    console.print(table)


@app.command()
def new(
    name: str = typer.Argument(..., help="Имя сервиса"),
    visibility: str = typer.Argument("public", help="Видимость сервиса (public/internal)"),
):
    """Создать новый сервис из шаблона"""
    config = get_config()
    
    if visibility not in ["public", "internal"]:
        console.print("[red]❌ visibility должен быть 'public' или 'internal'[/red]")
        raise typer.Exit(1)
    
    services_path = PROJECT_ROOT / config.get("services_path", "services") / visibility
    service_dir = services_path / name
    
    if service_dir.exists():
        console.print(f"[red]❌ Сервис '{name}' уже существует[/red]")
        raise typer.Exit(1)
    
    # Создание директории
    service_dir.mkdir(parents=True, exist_ok=True)
    
    # Шаблон service.yml
    service_yml = {
        "name": name,
        "display_name": name.replace("-", " ").title(),
        "version": "1.0.0",
        "description": f"Сервис {name}",
        "maintainer": "team@example.com",
        "type": "docker-compose",
        "visibility": visibility,
        "routing": [
            {
                "type": "subfolder",
                "base_domain": "apps.example.com",
                "path": f"/{name}",
                "strip_prefix": True,
                "internal_port": 8000,
            }
        ],
        "health": {
            "enabled": True,
            "endpoint": "/healthz",
            "interval": "30s",
        },
        "backup": {
            "enabled": False,
            "schedule": "0 2 * * *",
            "retention": 7,
        },
    }
    
    with open(service_dir / "service.yml", "w") as f:
        yaml.dump(service_yml, f, default_flow_style=False, allow_unicode=True)
    
    # Шаблон docker-compose.yml
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
    
    # Шаблон .env.example
    env_example = """# Переменные окружения сервиса
ENV=production
DATABASE_URL=postgresql://user:pass@db:5432/dbname
"""
    
    with open(service_dir / ".env.example", "w") as f:
        f.write(env_example)
    
    # Создание .env из .env.example
    with open(service_dir / ".env", "w") as f:
        f.write(env_example)
    
    # Шаблон README.md
    readme = f"""# {name.replace("-", " ").title()}

## Описание

{service_yml['description']}

## Запуск

```bash
platform deploy {name}
```

## Логи

```bash
platform logs {name}
```
"""
    
    with open(service_dir / "README.md", "w") as f:
        f.write(readme)
    
    # Создание пустой директории для исходного кода
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
):
    """Задеплоить сервис"""
    services = get_services()
    
    if service not in services:
        console.print(f"[red]❌ Сервис '{service}' не найден[/red]")
        raise typer.Exit(1)
    
    service_path = services[service]["path"]
    
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
def stop(service: str = typer.Argument(..., help="Имя сервиса")):
    """Остановить сервис"""
    services = get_services()
    
    if service not in services:
        console.print(f"[red]❌ Сервис '{service}' не найден[/red]")
        raise typer.Exit(1)
    
    service_path = services[service]["path"]
    
    console.print(f"[blue]ℹ️  Остановка сервиса '{service}'...[/blue]")
    result = compose_cmd(service_path, "down")
    
    if result.returncode == 0:
        console.print(f"[green]✅ Сервис '{service}' остановлен[/green]")
    else:
        console.print(f"[red]❌ Ошибка остановки сервиса '{service}'[/red]")
        raise typer.Exit(1)


@app.command()
def restart(service: str = typer.Argument(..., help="Имя сервиса")):
    """Перезапустить сервис"""
    services = get_services()
    
    if service not in services:
        console.print(f"[red]❌ Сервис '{service}' не найден[/red]")
        raise typer.Exit(1)
    
    service_path = services[service]["path"]
    
    console.print(f"[blue]ℹ️  Перезапуск сервиса '{service}'...[/blue]")
    compose_cmd(service_path, "restart")
    console.print(f"[green]✅ Сервис '{service}' перезапущен[/green]")


@app.command()
def status(service: Optional[str] = typer.Argument(None, help="Имя сервиса (опционально)")):
    """Показать статус сервисов"""
    if service:
        services = get_services()
        if service not in services:
            console.print(f"[red]❌ Сервис '{service}' не найден[/red]")
            raise typer.Exit(1)
        
        service_path = services[service]["path"]
        status = get_service_status(service_path)
        
        console.print(f"\n[bold]Сервис:[/bold] {service}")
        console.print(f"[bold]Путь:[/bold] {service_path}")
        console.print(f"[bold]Статус:[/bold] {status}")
        
        # Попытка получить детальную информацию через Docker API
        try:
            client = docker.from_env()
            containers = client.containers.list(filters={"name": service})
            if containers:
                container = containers[0]
                stats = container.stats(stream=False)
                if "memory_stats" in stats:
                    memory = stats["memory_stats"]
                    if "usage" in memory and "limit" in memory:
                        memory_mb = memory["usage"] / 1024 / 1024
                        memory_limit_mb = memory["limit"] / 1024 / 1024
                        console.print(f"[bold]Память:[/bold] {memory_mb:.1f}MB / {memory_limit_mb:.1f}MB")
        except Exception:
            pass
    else:
        # Показать все сервисы
        list()


@app.command()
def logs(
    service: str = typer.Argument(..., help="Имя сервиса"),
    lines: int = typer.Option(100, "--lines", "-n", help="Количество строк"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Следить за логами"),
):
    """Просмотр логов сервиса"""
    services = get_services()
    
    if service not in services:
        console.print(f"[red]❌ Сервис '{service}' не найден[/red]")
        raise typer.Exit(1)
    
    service_path = services[service]["path"]
    
    args = ["logs", f"--tail={lines}"]
    if follow:
        args.append("-f")
    
    compose_cmd(service_path, *args)


@app.command()
def backup(
    service: str = typer.Argument(..., help="Имя сервиса"),
):
    """Создать бэкап сервиса"""
    config = get_config()
    services = get_services()
    
    if service not in services:
        console.print(f"[red]❌ Сервис '{service}' не найден[/red]")
        raise typer.Exit(1)
    
    service_path = services[service]["path"]
    service_yml_path = service_path / "service.yml"
    
    # Чтение service.yml
    if not service_yml_path.exists():
        console.print(f"[red]❌ Файл service.yml не найден[/red]")
        raise typer.Exit(1)
    
    with open(service_yml_path) as f:
        service_config = yaml.safe_load(f)
    
    backup_config = service_config.get("backup", {})
    if not backup_config.get("enabled", False):
        console.print("[yellow]⚠️  Бэкапы не включены в service.yml[/yellow]")
        raise typer.Exit(1)
    
    # Попытка создать бэкап через Master Service API
    master_url = "http://localhost:8001"
    
    try:
        response = requests.post(
            f"{master_url}/api/backups/service/{service}/backup",
            json={"reason": "manual"},
            timeout=10,
        )
        
        if response.status_code == 200:
            result = response.json()
            console.print(f"[green]✅ Бэкап создан: {result.get('name', 'N/A')}[/green]")
        else:
            console.print(f"[yellow]⚠️  API вернул статус {response.status_code}. Попробуйте вручную.[/yellow]")
    except requests.exceptions.ConnectionError:
        console.print("[yellow]⚠️  Master Service недоступен. Запустите бэкап вручную через restic.[/yellow]")
    except Exception as e:
        console.print(f"[yellow]⚠️  Ошибка: {e}[/yellow]")


@app.command()
def info():
    """Показать информацию о платформе"""
    config = get_config()
    
    console.print("\n[bold blue]Platform Master Service[/bold blue]\n")
    console.print(f"[bold]Project Root:[/bold] {PROJECT_ROOT}")
    console.print(f"[bold]Environment:[/bold] {config.get('environment', 'unknown')}")
    console.print(f"[bold]Core Path:[/bold] {config.get('core_path', '_core')}")
    console.print(f"[bold]Services Path:[/bold] {config.get('services_path', 'services')}")
    
    # Подсчёт сервисов
    services = get_services()
    core_services = sum(1 for s in services.values() if s["type"] == "core")
    public_services = sum(1 for s in services.values() if s["type"] == "public")
    internal_services = sum(1 for s in services.values() if s["type"] == "internal")
    
    console.print(f"\n[bold]Всего сервисов:[/bold] {len(services)}")
    console.print(f"  - Core: {core_services}")
    console.print(f"  - Public: {public_services}")
    console.print(f"  - Internal: {internal_services}")


@app.command()
def reload():
    """Перезагрузить конфигурацию Caddy"""
    console.print("[blue]ℹ️  Перезагрузка Caddy...[/blue]")
    
    try:
        result = subprocess.run(
            ["docker", "exec", "caddy", "caddy", "reload", "--config", "/etc/caddy/Caddyfile"],
            capture_output=True,
            text=True,
        )
        
        if result.returncode == 0:
            console.print("[green]✅ Caddy перезапущен[/green]")
        else:
            console.print(f"[red]❌ Ошибка: {result.stderr}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]❌ Ошибка: {e}[/red]")
        raise typer.Exit(1)


def main():
    """Точка входа CLI"""
    app()


if __name__ == "__main__":
    main()
