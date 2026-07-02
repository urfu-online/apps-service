"""Команды управления бэкапами Kopia: backup create/list/restore/delete.

Хелперы остаются в ``apps_platform.cli``; обращения идут через ``_cli``.
"""

from __future__ import annotations

from apps_platform import cli as _cli
from apps_platform.api_client import get_api_client

app = _cli.app

# Группа команд для управления бэкапами Kopia
backup_app = _cli.typer.Typer(name="backup", help="Управление бэкапами Kopia")
app.add_typer(backup_app)


@backup_app.callback(invoke_without_command=True)
def backup_callback(
    ctx: _cli.typer.Context,
    service: str = _cli.typer.Argument(..., help="Имя сервиса (устаревший синтаксис)"),
):
    """Создать бэкап сервиса (устаревший синтаксис)."""
    if ctx.invoked_subcommand is None:
        _cli.console.print(
            "[yellow]⚠️  Команда 'platform backup' устарела, "
            "используйте 'platform backup create'[/yellow]"
        )
        _cli.asyncio.run(_backup_create_async(service))


async def _ensure_backup_enabled(service_name: str) -> None:
    """Проверка, что бэкапы включены в service.yml."""
    services = _cli.get_services()
    service_path = _cli.get_service_or_fail(services, service_name)
    service_yml_path = service_path / "service.yml"

    if not service_yml_path.exists():
        _cli.console.print("[red]❌ Файл service.yml не найден[/red]")
        raise _cli.typer.Exit(1)

    service_config = await _cli.asyncio.to_thread(
        lambda: _cli.yaml.safe_load(service_yml_path.read_text(encoding="utf-8"))
    )

    backup_config = service_config.get("backup", {})
    if not backup_config.get("enabled", False):
        _cli.console.print("[yellow]⚠️  Бэкапы не включены в service.yml[/yellow]")
        raise _cli.typer.Exit(1)


@backup_app.command("create")
def backup_create(
    service: str = _cli.typer.Argument(..., help="Имя сервиса"),
) -> None:
    """Создать бэкап сервиса (Kopia)."""
    _cli.asyncio.run(_backup_create_async(service))


async def _backup_create_async(service_name: str) -> None:
    """Асинхронная реализация создания бэкапа."""
    await _ensure_backup_enabled(service_name)

    try:
        async with get_api_client() as client:
            result = await client.create_backup(service_name)
            _cli.console.print(f"[green]✅ Бэкап создан: {result.get('snapshot_id', 'N/A')}[/green]")
            if "message" in result:
                _cli.console.print(f"[blue]ℹ️  {result['message']}[/blue]")
    except Exception as e:
        _cli.console.print(f"[red]❌ Ошибка: {e}[/red]")
        raise _cli.typer.Exit(1) from e


@backup_app.command("list")
def backup_list(
    service: str = _cli.typer.Argument(..., help="Имя сервиса"),
) -> None:
    """Показать список снапшотов сервиса."""
    _cli.asyncio.run(_backup_list_async(service))


async def _backup_list_async(service_name: str) -> None:
    """Асинхронная реализация списка снапшотов."""
    await _ensure_backup_enabled(service_name)

    try:
        async with get_api_client() as client:
            snapshots = await client.list_backups(service_name)
            if not snapshots:
                _cli.console.print("[yellow]⚠️  Снапшотов не найдено[/yellow]")
                return

            table = _cli.Table(title=f"Снапшоты сервиса {service_name}")
            table.add_column("ID", style="cyan")
            table.add_column("Создан", style="magenta")
            table.add_column("Размер", style="blue")
            table.add_column("Статус", style="yellow")

            for snap in snapshots:
                snapshot_id = snap.get("snapshot_id", "N/A")
                created_at = snap.get("created_at", "N/A")
                size_bytes = snap.get("size_bytes", 0)
                status = snap.get("status", "unknown")

                # Форматирование размера
                if size_bytes >= 1024**3:
                    size_str = f"{size_bytes / (1024**3):.2f} GB"
                elif size_bytes >= 1024**2:
                    size_str = f"{size_bytes / (1024**2):.2f} MB"
                elif size_bytes >= 1024:
                    size_str = f"{size_bytes / 1024:.2f} KB"
                else:
                    size_str = f"{size_bytes} B"

                table.add_row(snapshot_id, created_at, size_str, status)

            _cli.console.print(table)
    except Exception as e:
        _cli.console.print(f"[red]❌ Ошибка: {e}[/red]")
        raise _cli.typer.Exit(1) from e


@backup_app.command("restore")
def backup_restore(
    service: str = _cli.typer.Argument(..., help="Имя сервиса"),
    snapshot_id: str = _cli.typer.Argument(..., help="ID снапшота"),
    target: str = _cli.typer.Option(None, "--target", "-t", help="Целевой путь (опционально)"),
    force: bool = _cli.typer.Option(False, "--force", "-f", help="Принудительное восстановление"),
) -> None:
    """Восстановить снапшот сервиса."""
    _cli.asyncio.run(_backup_restore_async(service, snapshot_id, target, force))


async def _backup_restore_async(
    service_name: str,
    snapshot_id: str,
    target: str | None,
    force: bool,
) -> None:
    """Асинхронная реализация восстановления."""
    await _ensure_backup_enabled(service_name)

    try:
        async with get_api_client() as client:
            result = await client.restore_backup(service_name, snapshot_id, target, force)
            _cli.console.print(f"[green]✅ Восстановление запущено: {result.get('operation_id', 'N/A')}[/green]")
            if "message" in result:
                _cli.console.print(f"[blue]ℹ️  {result['message']}[/blue]")
    except Exception as e:
        _cli.console.print(f"[red]❌ Ошибка: {e}[/red]")
        raise _cli.typer.Exit(1) from e


@backup_app.command("delete")
def backup_delete(
    snapshot_id: str = _cli.typer.Argument(..., help="ID снапшота"),
    force: bool = _cli.typer.Option(False, "--force", "-f", help="Пропустить подтверждение"),
) -> None:
    """Удалить снапшот."""
    if not force:
        confirm = _cli.typer.confirm(f"Вы уверены, что хотите удалить снапшот {snapshot_id}?")
        if not confirm:
            _cli.console.print("[yellow]⚠️ Операция отменена[/yellow]")
            raise _cli.typer.Exit(0)
    _cli.asyncio.run(_backup_delete_async(snapshot_id))


async def _backup_delete_async(snapshot_id: str) -> None:
    """Асинхронная реализация удаления снапшота."""
    try:
        async with get_api_client() as client:
            result = await client.delete_backup(snapshot_id)
            _cli.console.print(f"[green]✅ Снапшот удалён: {result.get('message', 'Успешно')}[/green]")
    except Exception as e:
        _cli.console.print(f"[red]❌ Ошибка: {e}[/red]")
        raise _cli.typer.Exit(1) from e
