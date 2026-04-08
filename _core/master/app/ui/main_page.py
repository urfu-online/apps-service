"""Главная страница дашборда Platform Manager."""
import asyncio
from nicegui import ui

from app.ui.components.base import (
    create_header,
    create_stat_card,
    create_status_chip,
    create_icon_button,
    create_empty_state,
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

    # Таблица сервисов с пагинацией (вместо карточек — избегаем WebSocket overflow)
    with ui.column().classes('w-full px-6 mt-6'):
        ui.label('Сервисы').classes('text-h6 font-medium mb-3')

        with ui.tabs().classes('w-full') as tabs:
            tab_all = ui.tab('Все')
            tab_public = ui.tab('Публичные')
            tab_internal = ui.tab('Внутренние')

        with ui.tab_panels(tabs, value=tab_all).classes('w-full'):
            with ui.tab_panel(tab_all):
                _render_services_table(services.values())

            with ui.tab_panel(tab_public):
                public_services = [s for s in services.values() if s.visibility == "public"]
                _render_services_table(public_services)

            with ui.tab_panel(tab_internal):
                internal_services = [s for s in services.values() if s.visibility == "internal"]
                _render_services_table(internal_services)


def _render_services_table(services):
    """Рендер таблицы сервисов с пагинацией (эффективно для WebSocket)."""
    if not services:
        create_empty_state(
            icon='📭',
            message='Нет сервисов для отображения',
            action_label='Обновить',
            on_action=lambda: ui.navigate.reload()
        )
        return

    columns = [
        {'name': 'status', 'label': '', 'field': 'status', 'align': 'center', 'style': 'width: 40px'},
        {'name': 'name', 'label': 'Название', 'field': 'name', 'align': 'left'},
        {'name': 'version', 'label': 'Версия', 'field': 'version', 'align': 'center', 'style': 'width: 80px'},
        {'name': 'routing', 'label': 'Маршруты', 'field': 'routing', 'align': 'left'},
        {'name': 'visibility', 'label': 'Тип', 'field': 'visibility', 'align': 'center', 'style': 'width: 100px'},
        {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'center', 'style': 'width: 120px'},
    ]

    rows = []
    for service in services:
        rows.append({
            'name': service.display_name or service.name,
            'version': service.version or '—',
            'visibility': service.visibility,
            'routing': _format_routing(service.routing),
            'service_name': service.name,
            'status': service.status,
        })

    table = ui.table(
        columns=columns,
        rows=rows,
        row_key='name'
    ).classes('w-full').props('flat bordered').props(
        'pagination-label="Строк на странице" pagination-rows-per-page-options="5,10,20,50" '
        'pagination-rows-per-page=10'
    )

    # Статус бейдж
    table.add_slot('body-cell-status', '''
        <q-td :props="props">
            <q-badge :color="props.row.status === 'running' ? 'positive' :
                           props.row.status === 'stopped' ? 'negative' :
                           props.row.status === 'partial' ? 'warning' : 'grey'">
                {{ props.row.status === 'running' ? '▶' :
                   props.row.status === 'stopped' ? '■' :
                   props.row.status === 'partial' ? '●' : '?' }}
            </q-badge>
        </q-td>
    ''')

    # Visibility бейдж
    table.add_slot('body-cell-visibility', '''
        <q-td :props="props">
            <q-badge outline :color="props.row.visibility === 'public' ? 'info' : 'secondary'">
                {{ props.row.visibility === 'public' ? '🌍 Публичный' : '🔒 Внутренний' }}
            </q-badge>
        </q-td>
    ''')

    # Кнопки действий
    table.add_slot('body-cell-actions', '''
        <q-td :props="props">
            <div class="row q-gutter-xs justify-center">
                <q-btn flat dense round icon="visibility"
                       @click="$parent.$emit('view', props.row)"
                       color="primary" />
                <q-btn flat dense round icon="refresh"
                       @click="$parent.$emit('restart', props.row)" />
                <q-btn flat dense round :icon="props.row.status === 'running' ? 'stop' : 'play_arrow'"
                       @click="$parent.$emit('toggle', props.row)"
                       :color="props.row.status === 'running' ? 'negative' : 'positive'" />
            </div>
        </q-td>
    ''')

    table.on('view', lambda e: ui.navigate.to(f'/services/{e.args["service_name"]}'))
    table.on('restart', lambda e: asyncio.ensure_future(_handle_action(e.args["service_name"], 'restart')))
    table.on('toggle', lambda e: _handle_toggle(e.args))


def _handle_toggle(args: dict):
    """Обработка кнопки запуска/остановки."""
    service_name = args["service_name"]
    status = args.get("status", "unknown")
    action = 'deploy' if status != 'running' else 'stop'
    asyncio.ensure_future(_handle_action(service_name, action))


def _format_routing(routing) -> str:
    """Форматирование информации о маршрутизации."""
    if not routing:
        return "—"

    parts = []
    for route in routing:
        if route.type == 'domain':
            parts.append(f"🌐 {route.domain}")
        elif route.type == 'subfolder':
            parts.append(f"📁 {route.base_domain}{route.path}")
        elif route.type == 'port':
            parts.append(f"🔌 :{route.port}")

    return " • ".join(parts) if parts else "—"


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
