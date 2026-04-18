"""
CLI утилита для управления платформой Platform Master Service
"""
import os
import subprocess
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

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

# Глобальная конфигурация (инициализируется однократно при импорте)
PROJECT_ROOT = Path(os.getenv("OPS_PROJECT_ROOT", str(Path.cwd())))
CONFIG_FILE: Path | None = None


def _deep_merge(base: dict, override: dict) -> dict:
    """Рекурсивное слияние словарей конфигурации."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


@lru_cache(maxsize=1)
def get_config() -> dict:
    """Загрузка конфигурации — кэшируется на время процесса."""
    config_candidates = [
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
def docker_client():
    """Контекстный менеджер для Docker client."""
    client = docker.from_env()
    try:
        yield client
    finally:
        client.close()


def get_services() -> dict:
    """Сканирование сервисов в проекте."""
    config = get_config()
    services = {}
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


def compose_cmd(service_path: Path, *args: str) -> subprocess.CompletedProcess:
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
            capture_output=True, text=True, check=True, timeout=10
        )
        statuses = {}
        for line in res.stdout.strip().splitlines():
            if not line:
                continue
            import json
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


def get_service_status(service_path: Path) -> str:
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", str(service_path / "docker-compose.yml"), "ps", "-q"],
            capture_output=True, text=True, cwd=service_path, timeout=10
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


def get_service_or_fail(services: dict, service_name: str) -> Path:
    """Проверка существования сервиса и возврат пути."""
    if service_name not in services:
        console.print(f"[red]❌ Сервис '{service_name}' не найден[/red]")
        raise typer.Exit(1)
    return services[service_name]["path"]


def validate_service_name(name: str) -> str:
    """Валидация имени на path traversal и недопустимые символы."""
    if not name or ".." in name or "/" in name or "\\" in name or " " in name or name.startswith("."):
        console.print("[red]❌ Некорректное имя сервиса (допускаются только буквы, цифры, дефисы)[/red]")
        raise typer.Exit(1)
    return name.lower()


@app.command()
def list(
    visibility: str | None = typer.Option(None, "--visibility", "-v", help="Фильтр по видимости (public/internal)"),
    status_filter: str | None = typer.Option(None, "--status", "-s", help="Фильтр по статусу (running/stopped)"),
):
    """Показать все сервисы."""
    services = get_services()
    container_map = _get_all_container_statuses()  # Один запрос вместо N

    table = Table(title="Сервисы платформы")
    table.add_column("Service", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Path", style="green")
    table.add_column("Status", style="yellow")

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

        short_path = str(info["path"].relative_to(PROJECT_ROOT))
        status_style = "green" if "running" in svc_status else "red"
        table.add_row(name, info["type"], short_path, f"[{status_style}]{svc_status}[/{status_style}]")

    console.print(table)


@app.command()
def new(
    name: str = typer.Argument(..., help="Имя сервиса"),
    visibility: str = typer.Argument("public", help="Видимость сервиса (public/internal)"),
):
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
):
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
def stop(service: str = typer.Argument(..., help="Имя сервиса")):
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
def restart(service: str = typer.Argument(..., help="Имя сервиса")):
    """Перезапустить сервис."""
    service_path = get_service_or_fail(get_services(), service)

    console.print(f"[blue]ℹ️  Перезапуск сервиса '{service}'...[/blue]")
    compose_cmd(service_path, "restart")
    console.print(f"[green]✅ Сервис '{service}' перезапущен[/green]")


@app.command()
def status(service: str | None = typer.Argument(None, help="Имя сервиса (опционально)")):
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
            pass
    else:
        list()


@app.command()
def logs(
    service: str = typer.Argument(..., help="Имя сервиса"),
    lines: int = typer.Option(100, "--lines", "-n", help="Количество строк"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Следить за логами"),
):
    """Просмотр логов сервиса."""
    service_path = get_service_or_fail(get_services(), service)

    args = ["logs", f"--tail={lines}"]
    if follow:
        args.append("-f")

    compose_cmd(service_path, *args)


@app.command()
def backup(service: str = typer.Argument(..., help="Имя сервиса")):
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
            timeout=10,
        )
        if response.status_code == 200:
            result = response.json()
            console.print(f"[green]✅ Бэкап создан: {result.get('name', 'N/A')}[/green]")
            raise typer.Exit(0)
        else:
            console.print(f"[red]❌ API вернул статус {response.status_code}[/red]")
            raise typer.Exit(1)
    except requests.exceptions.ConnectionError:
        console.print("[red]❌ Master Service недоступен. Запустите бэкап вручную через restic.[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]❌ Ошибка: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def info():
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
    container: str = typer.Option("caddy", "--container", "-c", help="Имя контейнера Caddy"),
):
    """Перезагрузить конфигурацию Caddy."""
    console.print(f"[blue]ℹ️  Перезагрузка Caddy в контейнере '{container}'...[/blue]")
    try:
        result = subprocess.run(
            ["docker", "exec", container, "caddy", "reload", "--config", "/etc/caddy/Caddyfile"],
            capture_output=True, text=True, check=True
        )
        console.print("[green]✅ Caddy перезапущен[/green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]❌ Ошибка: {e.stderr.strip()}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]❌ Ошибка: {e}[/red]")
        raise typer.Exit(1)


def main():
    """Точка входа CLI."""
    app()


if __name__ == "__main__":
    main()