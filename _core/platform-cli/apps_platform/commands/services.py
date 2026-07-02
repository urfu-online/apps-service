"""Сервисные команды platform-cli: deploy, stop, restart, status, logs, info, reload.

Команды ``list`` и ``new`` вынесены в подмодули ``services_listing`` и
``services_create`` соответственно. Хелперы (``get_services``,
``compose_cmd``, ``get_service_or_fail``, ``get_service_status``, ...) остаются
в ``apps_platform.cli``; обращения к ним идут через ``_cli`` для совместимости
с патчами ``apps_platform.cli.<helper>`` в тестах.
"""

from __future__ import annotations

from apps_platform import cli as _cli

# Импорт подмодулей с тяжёлыми командами нужен для регистрации декораторов
# @app.command на ``apps_platform.cli.app`` при загрузке пакета ``commands``.
from . import services_create, services_listing  # noqa: F401

app = _cli.app


@app.command()
def deploy(
    service: str = _cli.typer.Argument(..., help="Имя сервиса"),
    build: bool = _cli.typer.Option(False, "--build", "-b", help="Пересобрать образы"),
    pull: bool = _cli.typer.Option(False, "--pull", "-p", help="Обновить образы"),
    dry_run: bool = _cli.typer.Option(
        False,
        "--dry-run",
        help="Показать план без выполнения docker compose.",
    ),
) -> None:
    """Задеплоить сервис."""
    with _cli.platform_lock():
        service_path = _cli.get_service_or_fail(_cli.get_services(), service)

        args = ["up", "-d"]
        if build:
            args.append("--build")
        if pull:
            args.append("--pull")

        if dry_run:
            _cli.console.print(
                f"[yellow]DRY-RUN:[/yellow] deploy '{service}' ({service_path}) "
                f"c командами: {' '.join(args)}"
            )
            _cli.compose_cmd(service_path, *args, dry_run=True)
            return

        _cli.console.print(f"[blue]ℹ️  Деплой сервиса '{service}'...[/blue]")
        result = _cli.compose_cmd(service_path, *args)

        if result.returncode == 0:
            _cli.console.print(f"[green]✅ Сервис '{service}' успешно задеплоен[/green]")
        else:
            _cli.console.print(f"[red]❌ Ошибка деплоя сервиса '{service}'[/red]")
            raise _cli.typer.Exit(1)


@app.command()
def stop(service: str = _cli.typer.Argument(..., help="Имя сервиса")) -> None:
    """Остановить сервис."""
    with _cli.platform_lock():
        service_path = _cli.get_service_or_fail(_cli.get_services(), service)

        _cli.console.print(f"[blue]ℹ️  Остановка сервиса '{service}'...[/blue]")
        result = _cli.compose_cmd(service_path, "down")

        if result.returncode == 0:
            _cli.console.print(f"[green]✅ Сервис '{service}' остановлен[/green]")
        else:
            _cli.console.print(f"[red]❌ Ошибка остановки сервиса '{service}'[/red]")
            raise _cli.typer.Exit(1)


@app.command()
def restart(service: str = _cli.typer.Argument(..., help="Имя сервиса")) -> None:
    """Перезапустить сервис."""
    with _cli.platform_lock():
        service_path = _cli.get_service_or_fail(_cli.get_services(), service)

        _cli.console.print(f"[blue]ℹ️  Перезапуск сервиса '{service}'...[/blue]")
        _cli.compose_cmd(service_path, "restart")
        _cli.console.print(f"[green]✅ Сервис '{service}' перезапущен[/green]")


@app.command()
def status(service: str | None = _cli.typer.Argument(None, help="Имя сервиса (опционально)")) -> None:
    """Показать статус сервисов."""
    if service:
        service_path = _cli.get_service_or_fail(_cli.get_services(), service)
        svc_status = _cli.get_service_status(service_path)

        _cli.console.print(f"\n[bold]Сервис:[/bold] {service}")
        _cli.console.print(f"[bold]Путь:[/bold] {service_path}")
        _cli.console.print(f"[bold]Статус:[/bold] {svc_status}")

        try:
            with _cli.docker_client() as client:
                containers = client.containers.list(filters={"name": service})
                if containers:
                    container = containers[0]
                    stats = container.stats(stream=False)
                    if "memory_stats" in stats:
                        memory = stats["memory_stats"]
                        if "usage" in memory and "limit" in memory:
                            memory_mb = memory["usage"] / (1024 * 1024)
                            memory_limit_mb = memory["limit"] / (1024 * 1024)
                            _cli.console.print(
                                f"[bold]Память:[/bold] {memory_mb:.1f}MB / {memory_limit_mb:.1f}MB"
                            )
        except Exception as exc:
            _cli.logger.debug("memory stats skipped: %s", exc)
    else:
        services_listing.list_services()


@app.command()
def logs(
    service: str = _cli.typer.Argument(..., help="Имя сервиса"),
    lines: int = _cli.typer.Option(100, "--lines", "-n", help="Количество строк"),
    follow: bool = _cli.typer.Option(False, "--follow", "-f", help="Следить за логами"),
) -> None:
    """Просмотр логов сервиса."""
    service_path = _cli.get_service_or_fail(_cli.get_services(), service)

    args = ["logs", f"--tail={lines}"]
    if follow:
        args.append("-f")

    _cli.compose_cmd(service_path, *args)


@app.command()
def info() -> None:
    """Показать информацию о платформе."""
    config = _cli.get_config()
    _cli.console.print("\n[bold blue]Platform Master Service[/bold blue]\n")
    _cli.console.print(f"[bold]Project Root:[/bold] {_cli.get_project_root()}")
    _cli.console.print(f"[bold]Environment:[/bold] {config.get('environment', 'unknown')}")
    _cli.console.print(f"[bold]Core Path:[/bold] {config.get('core_path', '_core')}")
    _cli.console.print(f"[bold]Services Path:[/bold] {config.get('services_path', 'services')}")

    services = _cli.get_services()
    core_count = sum(1 for s in services.values() if s["type"] == "core")
    public_count = sum(1 for s in services.values() if s["type"] == "public")
    internal_count = sum(1 for s in services.values() if s["type"] == "internal")

    _cli.console.print(f"\n[bold]Всего сервисов:[/bold] {len(services)}")
    _cli.console.print(f"  - Core: {core_count}")
    _cli.console.print(f"  - Public: {public_count}")
    _cli.console.print(f"  - Internal: {internal_count}")


@app.command()
def reload(
    container: str = _cli.typer.Option(
        _cli.CADDY_DEFAULT_CONTAINER_NAME, "--container", "-c", help="Имя контейнера Caddy"
    ),
) -> None:
    """Перезагрузить конфигурацию Caddy."""
    if not container or not container.replace("-", "").replace("_", "").isalnum():
        _cli.console.print("[red]❌ Неверное имя контейнера[/red]")
        raise _cli.typer.Exit(1)

    try:
        check_result = _cli.subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=True,
        )
        running_containers = check_result.stdout.strip().split("\n")
        if container not in running_containers:
            _cli.console.print(f"[red]❌ Контейнер '{container}' не найден или не запущен[/red]")
            _cli.console.print("[yellow]Доступные контейнеры:[/yellow]")
            for c in running_containers:
                if c:
                    _cli.console.print(f"  - {c}")
            raise _cli.typer.Exit(1)
    except _cli.subprocess.CalledProcessError as e:
        _cli.console.print("[red]❌ Ошибка проверки контейнеров Docker[/red]")
        raise _cli.typer.Exit(1) from e

    _cli.console.print(f"[blue]ℹ️  Перезагрузка Caddy в контейнере '{container}'...[/blue]")
    try:
        _cli.subprocess.run(
            ["docker", "exec", container, "caddy", "reload", "--config", "/etc/caddy/Caddyfile"],
            capture_output=True,
            text=True,
            check=True,
        )
        _cli.console.print("[green]✅ Caddy перезапущен[/green]")
    except _cli.subprocess.CalledProcessError as e:
        _cli.console.print(f"[red]❌ Ошибка: {e.stderr.strip()}[/red]")
        raise _cli.typer.Exit(1) from e
    except Exception:
        _cli.logger.exception("Unhandled error while reloading Caddy")
        _cli.console.print("[red]❌ Неизвестная ошибка при перезагрузке Caddy[/red]")
        raise _cli.typer.Exit(1) from None
