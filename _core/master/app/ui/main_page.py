"""Главная страница дашборда Platform Manager."""
import asyncio
from nicegui import ui

from app.ui.components.base import (
    create_header,
    create_stat_card,
    create_status_chip,
    create_icon_button,
)


async def render_main_page():
    """Рендер главной страницы дашборда."""
    from app.main import app

    discovery = app.state.discovery
    services = discovery.services

    # Статистика
    total = len(services)
    running = sum(1 for s in services.values() if s.status == "running")
    stopped = sum(1 for s in services.values() if s.status == "stopped")
    public = sum(1 for s in services.values() if s.visibility == "public")

    # Заголовок
    create_header()

    # Карточки статистики в одну линию
    with ui.row().classes('w-full px-6 gap-4 mt-4'):
        create_stat_card('Всего сервисов', str(total), '📦', 'primary')
        create_stat_card('Запущено', str(running), '🟢', 'positive')
        create_stat_card('Остановлено', str(stopped), '🔴', 'negative')
        create_stat_card('Публичных', str(public), '🌍', 'info')

    # Навигация по сервисам
    with ui.column().classes('w-full px-6 mt-6'):
        ui.label('Сервисы').classes('text-h6 font-medium mb-3')
        
        with ui.tabs().classes('w-full') as tabs:
            tab_all = ui.tab('Все')
            tab_public = ui.tab('Публичные')
            tab_internal = ui.tab('Внутренние')

        with ui.tab_panels(tabs, value=tab_all).classes('w-full'):
            with ui.tab_panel(tab_all):
                await _render_services_list(services.values())

            with ui.tab_panel(tab_public):
                public_services = [s for s in services.values() if s.visibility == "public"]
                await _render_services_list(public_services)

            with ui.tab_panel(tab_internal):
                internal_services = [s for s in services.values() if s.visibility == "internal"]
                await _render_services_list(internal_services)


async def _render_services_list(services):
    """Рендер списка сервисов в виде карточек."""
    if not services:
        _render_empty_state()
        return

    with ui.column().classes('w-full gap-3'):
        for service in services:
            await _render_service_row(service)


async def _render_service_row(service):
    """Рендер строки сервиса."""
    status_colors = {
        'running': 'bg-positive/10 text-positive',
        'stopped': 'bg-negative/10 text-negative',
        'partial': 'bg-warning/10 text-warning',
        'unknown': 'bg-grey/10 text-grey',
    }
    
    status_icon = {
        'running': 'play_circle',
        'stopped': 'stop_circle',
        'partial': 'remove_circle',
        'unknown': 'help_circle',
    }.get(service.status, 'help_circle')

    with ui.card().classes('w-full p-4').props('flat bordered'):
        with ui.row().classes('w-full items-center'):
            # Индикатор статуса
            with ui.column().classes('items-center justify-center w-12'):
                ui.icon(status_icon).classes(f'text-2xl {status_colors.get(service.status, "")}')

            # Информация о сервисе
            with ui.column().classes('flex-1 ml-2'):
                ui.label(service.display_name or service.name).classes('text-subtitle1 font-medium')
                
                # Маршруты
                routing_info = _format_routing(service.routing)
                if routing_info:
                    ui.label(routing_info).classes('text-caption text-grey-7')

            # Видимость
            create_status_chip('public' if service.visibility == 'public' else 'internal')

            # Кнопки действий
            with ui.row().classes('gap-1'):
                create_icon_button(
                    'visibility',
                    lambda s=service: ui.navigate.to(f'/services/{s.name}'),
                    tooltip='Просмотр'
                )
                create_icon_button(
                    'refresh',
                    lambda s=service: asyncio.ensure_future(_handle_action(s.name, 'restart')),
                    tooltip='Перезапустить'
                )
                if service.status == 'running':
                    create_icon_button(
                        'stop_circle',
                        lambda s=service: asyncio.ensure_future(_handle_action(s.name, 'stop')),
                        color='negative',
                        tooltip='Остановить'
                    )
                else:
                    create_icon_button(
                        'play_circle',
                        lambda s=service: asyncio.ensure_future(_handle_action(s.name, 'deploy')),
                        color='positive',
                        tooltip='Запустить'
                    )


def _format_routing(routing) -> str:
    """Форматирование информации о маршрутизации."""
    if not routing:
        return ""
    
    parts = []
    for route in routing:
        if route.type == 'domain':
            parts.append(f"{route.domain}")
        elif route.type == 'subfolder':
            parts.append(f"{route.base_domain}{route.path}")
        elif route.type == 'port':
            parts.append(f":{route.port}")
    
    return " • ".join(parts) if parts else ""


def _render_empty_state():
    """Рендер состояния 'нет сервисов'."""
    from app.ui.components.base import create_empty_state
    create_empty_state(
        icon='📭',
        message='Нет сервисов для отображения',
        action_label='Обновить',
        on_action=lambda: ui.navigate.reload()
    )


async def _handle_action(service_name: str, action: str):
    """Обработка действий с сервисом."""
    from app.main import app

    service = app.state.discovery.get_service(service_name)
    if not service:
        ui.notify(f'Сервис {service_name} не найден', type='negative')
        return

    actions = {
        'deploy': ('Запуск...', app.state.docker.deploy_service),
        'restart': ('Перезапуск...', app.state.docker.restart_service),
        'stop': ('Остановка...', app.state.docker.stop_service),
    }

    action_label, action_func = actions.get(action, ('Действие...', None))
    if not action_func:
        return

    ui.notify(f'{action_label} {service_name}...', type='info')
    result = await action_func(service)

    if result.get('success'):
        action_done = {'deploy': 'запущен', 'restart': 'перезапущен', 'stop': 'остановлен'}.get(action, 'готово')
        ui.notify(f'{service_name} {action_done}', type='positive')
        ui.navigate.reload()
    else:
        msg = result.get('message', 'Неизвестная ошибка')
        ui.notify(f'Ошибка: {msg}', type='negative')
