from nicegui import ui
from datetime import datetime
from typing import List

from app.services.discovery import ServiceManifest


async def render_services_page():
    """Рендер страницы управления сервисами"""
    from app.main import app
    
    # Заголовок
    with ui.row().classes('w-full items-center'):
        ui.label('Services').classes('text-h4')
        ui.space()
        ui.button('Refresh', on_click=lambda: ui.navigate.reload()).classes('ml-auto')
    
    # Получаем список сервисов
    services = list(app.state.discovery.services.values())
    
    # Фильтры
    with ui.row().classes('w-full items-center'):
        search_input = ui.input('Search').classes('mr-2')
        visibility_select = ui.select(
            options=['all', 'public', 'internal'], 
            value='all',
            label='Visibility'
        ).classes('mr-2')
        
        ui.button('Apply Filters', on_click=lambda: apply_filters(
            search_input.value, 
            visibility_select.value
        ))
    
    # Таблица сервисов
    await render_services_table(services)


async def apply_filters(search: str, visibility: str):
    """Применение фильтров к списку сервисов"""
    from app.main import app
    
    services = list(app.state.discovery.services.values())
    
    # Применяем фильтры
    if search:
        services = [s for s in services if search.lower() in s.name.lower() or 
                   (s.display_name and search.lower() in s.display_name.lower())]
    
    if visibility != 'all':
        services = [s for s in services if s.visibility == visibility]
    
    # Обновляем таблицу
    # В реальной реализации здесь будет обновление таблицы
    ui.notify(f'Filtered to {len(services)} services')


async def render_services_table(services: List[ServiceManifest]):
    """Рендер таблицы сервисов"""
    columns = [
        {'name': 'status', 'label': '', 'field': 'status', 'align': 'center'},
        {'name': 'name', 'label': 'Name', 'field': 'name'},
        {'name': 'version', 'label': 'Version', 'field': 'version'},
        {'name': 'visibility', 'label': 'Visibility', 'field': 'visibility'},
        {'name': 'type', 'label': 'Type', 'field': 'type'},
        {'name': 'actions', 'label': 'Actions', 'field': 'actions'},
    ]
    
    rows = []
    for service in services:
        status_icon = {
            'running': '🟢',
            'stopped': '🔴',
            'partial': '🟡',
            'unknown': '⚪'
        }.get(service.status, '⚪')
        
        rows.append({
            'status': status_icon,
            'name': service.display_name or service.name,
            'version': service.version,
            'visibility': '🌍' if service.visibility == 'public' else '🔒',
            'type': service.type,
            'service_name': service.name
        })
    
    table = ui.table(columns=columns, rows=rows, row_key='name').classes('w-full')
    
    # Кастомные слоты для actions
    table.add_slot('body-cell-actions', '''
        <q-td :props="props">
            <q-btn flat dense icon="visibility" 
                   @click="$parent.$emit('view', props.row)" />
            <q-btn flat dense icon="play_arrow" 
                   @click="$parent.$emit('deploy', props.row)" />
            <q-btn flat dense icon="restart_alt" 
                   @click="$parent.$emit('restart', props.row)" />
            <q-btn flat dense icon="stop" color="negative"
                   @click="$parent.$emit('stop', props.row)" />
        </q-td>
    ''')
    
    table.on('view', lambda e: ui.navigate.to(f'/services/{e.args["service_name"]}'))
    table.on('deploy', lambda e: handle_deploy(e.args["service_name"]))
    table.on('restart', lambda e: handle_restart(e.args["service_name"]))
    table.on('stop', lambda e: handle_stop(e.args["service_name"]))


async def handle_deploy(service_name: str):
    """Обработка деплоя"""
    from app.main import app
    
    service = app.state.discovery.get_service(service_name)
    if service:
        ui.notify(f'Deploying {service_name}...', type='info')
        result = await app.state.docker.deploy_service(service)
        if result['success']:
            ui.notify(f'{service_name} deployed', type='positive')
        else:
            ui.notify(f'Deploy failed: {result["message"]}', type='negative')


async def handle_restart(service_name: str):
    """Обработка перезапуска"""
    from app.main import app
    
    service = app.state.discovery.get_service(service_name)
    if service:
        ui.notify(f'Restarting {service_name}...', type='info')
        result = await app.state.docker.restart_service(service)
        if result['success']:
            ui.notify(f'{service_name} restarted', type='positive')
        else:
            ui.notify(f'Restart failed: {result["message"]}', type='negative')


async def handle_stop(service_name: str):
    """Обработка остановки"""
    from app.main import app
    
    service = app.state.discovery.get_service(service_name)
    if service:
        ui.notify(f'Stopping {service_name}...', type='info')
        result = await app.state.docker.stop_service(service)
        if result['success']:
            ui.notify(f'{service_name} stopped', type='positive')
        else:
            ui.notify(f'Stop failed: {result["message"]}', type='negative')