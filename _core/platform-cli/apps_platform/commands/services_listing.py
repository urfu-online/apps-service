"""Команда ``platform list`` — отображение всех сервисов платформы.

Хелперы (``get_services``, ``_get_all_container_statuses``, ``_matches_service``,
``_get_actual_service_urls``, ``_get_ssl_verify``) остаются в ``apps_platform.cli``;
обращения к ним идут через ссылку ``_cli`` для совместимости с патчами тестов.
"""

from __future__ import annotations

from apps_platform import cli as _cli

app = _cli.app


@app.command("list")
def list_services(
    visibility: str | None = _cli.typer.Option(
        None, "--visibility", "-v", help="Фильтр по видимости (public/internal)"
    ),
    status_filter: str | None = _cli.typer.Option(
        None, "--status", "-s", help="Фильтр по статусу (running/stopped)"
    ),
    check_availability: bool = _cli.typer.Option(
        False, "--check", "-c", help="Проверять доступность сервисов"
    ),
    insecure: bool = _cli.typer.Option(
        False,
        "--insecure",
        help="Отключить проверку SSL сертификата при проверке доступности (также можно PLATFORM_SSL_VERIFY=false)",
    ),
) -> None:
    """Показать все сервисы."""
    services = _cli.get_services()
    container_map = _cli._get_all_container_statuses()

    ssl_verify = _cli._get_ssl_verify(insecure=insecure)

    table = _cli.Table(title="Сервисы платформы")
    table.add_column("Service", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("URL / Path", style="blue")
    table.add_column("Status", style="yellow")
    table.add_column("Available", style="green")

    for name, info in sorted(services.items()):
        if visibility and info["type"] != visibility:
            continue

        svc_status = "stopped"
        matching = [c for c in container_map if _cli._matches_service(c, name)]
        if matching:
            first_status = container_map[matching[0]].split()[0].lower()
            if first_status in ("up", "running", "restarting", "healthy"):
                svc_status = f"running ({len(matching)})"

        if status_filter:
            if status_filter == "running" and "running" not in svc_status:
                continue
            if status_filter == "stopped" and "running" in svc_status:
                continue

        service_path = info["path"]
        service_yml_path = service_path / "service.yml"

        service_config: dict = {}
        if service_yml_path.exists():
            try:
                with open(service_yml_path) as f:
                    service_config = _cli.yaml.safe_load(f) or {}
            except Exception:
                _cli.console.print(f"[yellow]⚠️  Не удалось прочитать service.yml для '{name}'[/yellow]")

        urls = _cli._get_actual_service_urls(name, service_path, service_config, project_root=_cli.get_project_root())

        url_display = "\n".join(urls[: _cli.MAX_URLS_DISPLAY])
        if len(urls) > _cli.MAX_URLS_DISPLAY:
            url_display += f"\n... +{len(urls) - _cli.MAX_URLS_DISPLAY} ещё"

        availability_status = "—"
        if check_availability and "running" in svc_status:
            checked_urls = []
            for url in urls:
                if "${" in url or "$PLATFORM_DOMAIN" in url:
                    continue
                checked_urls.append(url)
                try:
                    response = _cli.requests.get(url, timeout=_cli.AVAILABILITY_TIMEOUT, verify=ssl_verify)
                    if response.status_code < 500:
                        availability_status = "✓"
                        break
                    availability_status = f"✗ {response.status_code}"
                except _cli.requests.exceptions.ConnectionError:
                    availability_status = "✗ conn"
                except _cli.requests.exceptions.Timeout:
                    availability_status = "✗ timeout"
                except Exception as e:
                    availability_status = f"✗ {type(e).__name__}"

            if availability_status.startswith("✗") and checked_urls:
                pass
            elif not checked_urls and "running" in svc_status:
                availability_status = "?"
        elif "running" in svc_status:
            availability_status = "?"

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
            f"[{avail_style}]{availability_status}[/{avail_style}]",
        )

    _cli.console.print(table)
