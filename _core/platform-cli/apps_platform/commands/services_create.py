"""Команда ``platform new`` — создание нового сервиса из шаблона.

Хелперы (``get_config``, ``get_project_root``, ``validate_service_name``) остаются
в ``apps_platform.cli``; обращения идут через ``_cli``.
"""

from __future__ import annotations

from apps_platform import cli as _cli

app = _cli.app

_DEFAULT_BASE_DOMAIN = "apps.example.com"
_DEFAULT_INTERNAL_PORT = 8000
_DEFAULT_NETWORK_NAME = "platform_network"

_COMPOSE_TEMPLATE = """\
version: "3.8"
services:
  {container_name}:
    build: .
    container_name: {name}
    restart: unless-stopped
    ports:
      - "{port}:{port}"
    networks:
      - servicenet
      - platform
    environment:
      - ENV=production
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:{port}/healthz"]
      interval: 30s
      timeout: 10s
      retries: 3
networks:
  servicenet:
    name: {name}_network
  platform:
    external: true
    name: {network_name}
"""

_ENV_EXAMPLE = "# Переменные окружения сервиса\nENV=production\nDATABASE_URL=postgresql://user:pass@db:5432/dbname\n"

_ENV_TEMPLATE = "# Переменные окружения — скопируйте из .env.example и заполните\n"

_README_TEMPLATE = """# {title}
{description}
## Запуск
platform deploy {name}
## Логи
platform logs {name}
"""


@app.command()
def new(
    name: str = _cli.typer.Argument(..., help="Имя сервиса"),
    visibility: str = _cli.typer.Argument("public", help="Видимость сервиса (public/internal)"),
    dry_run: bool = _cli.typer.Option(
        False,
        "--dry-run",
        help="Показать план создания без записи файлов.",
    ),
) -> None:
    """Создать новый сервис из шаблона."""
    with _cli.platform_lock():
        _cli.validate_service_name(name)
        if visibility not in ("public", "internal"):
            _cli.console.print("[red]❌ visibility должен быть 'public' или 'internal'[/red]")
            raise _cli.typer.Exit(1)

        config = _cli.get_config()
        services_path = _cli.get_project_root() / config.get("services_path", "services") / visibility
        service_dir = services_path / name

        if service_dir.exists():
            _cli.console.print(f"[red]❌ Сервис '{name}' уже существует[/red]")
            raise _cli.typer.Exit(1)

        if dry_run:
            _cli.console.print(
                f"[yellow]DRY-RUN:[/yellow] would create service '{name}' (visibility={visibility}) "
                f"at {service_dir}"
            )
            _cli.console.print("Файлы, которые были бы созданы:")
            for rel in (
                "service.yml",
                "docker-compose.yml",
                ".env.example",
                ".env",
                "README.md",
                "src/__init__.py",
            ):
                _cli.console.print(f"  - {service_dir / rel}")
            return

        service_dir.mkdir(parents=True, exist_ok=True)

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
                    "base_domain": _DEFAULT_BASE_DOMAIN,
                    "path": f"/{name}",
                    "strip_prefix": True,
                    "internal_port": _DEFAULT_INTERNAL_PORT,
                }
            ],
            "health": {"enabled": True, "endpoint": "/healthz", "interval": "30s"},
            "backup": {"enabled": False, "schedule": "0 2 * * *", "retention": 7},
        }

        with open(service_dir / "service.yml", "w") as f:
            _cli.yaml.dump(service_yml, f, default_flow_style=False, allow_unicode=True)

        compose = _COMPOSE_TEMPLATE.format(
            name=name,
            container_name=name.replace("-", "_"),
            port=_DEFAULT_INTERNAL_PORT,
            network_name=_DEFAULT_NETWORK_NAME,
        )
        (service_dir / "docker-compose.yml").write_text(compose)
        (service_dir / ".env.example").write_text(_ENV_EXAMPLE)
        (service_dir / ".env").write_text(_ENV_TEMPLATE)
        (service_dir / "README.md").write_text(
            _README_TEMPLATE.format(
                title=name.replace("-", " ").title(),
                description=service_yml["description"],
                name=name,
            )
        )

        (service_dir / "src").mkdir(exist_ok=True)
        (service_dir / "src" / "__init__.py").touch()

        _cli.console.print(f"[green]✅ Сервис '{name}' создан в {service_dir}[/green]")
        _cli.console.print("\nСледующие шаги:")
        _cli.console.print(f"  1. Отредактируйте [cyan]{service_dir}/service.yml[/cyan]")
        _cli.console.print(f"  2. Добавьте код приложения в [cyan]{service_dir}/src/[/cyan]")
        _cli.console.print(f"  3. Задеплойте: [cyan]platform deploy {name}[/cyan]")
