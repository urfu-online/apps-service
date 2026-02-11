from nicegui import ui
from datetime import datetime


async def render_main_page():
    """Рендер главной страницы дашборда"""
    from app.main import app
    
    discovery = app.state.discovery
    services = discovery.services
    
    # Подсчет статистики
    total = len(services)
    running = len([s for s in services.values() if s.status == "running"])
    stopped = len([s for s in services.values() if s.status == "stopped"])
    public = len([s for s in services.values() if s.visibility == "public"])
    internal = len([s for s in services.values() if s.visibility == "internal"])
    
    with ui.header().classes('bg-primary'):
        ui.label('🚀 Platform Manager').classes('text-h4')
        ui.space()
        with ui.row():
            ui.button(icon='refresh', on_click=lambda: ui.navigate.reload())
            ui.button(icon='settings', on_click=lambda: ui.navigate.to('/settings'))
    
    with ui.row().classes('w-full justify-center gap-4 p-4'):
        # Карточки статистики
        with ui.card().classes('p-4'):
            ui.label('Total Services').classes('text-subtitle1')
            ui.label(str(total)).classes('text-h3 text-primary')
        
        with ui.card().classes('p-4'):
            ui.label('Running').classes('text-subtitle1')
            ui.label(str(running)).classes('text-h3 text-positive')
        
        with ui.card().classes('p-4'):
            ui.label('Stopped').classes('text-subtitle1')
            ui.label(str(stopped)).classes('text-h3 text-negative')
        
        with ui.card().classes('p-4'):
            ui.label('Public / Internal').classes('text-subtitle1')
            ui.label(f'{public} / {internal}').classes('text-h3')
    
    # Навигация
    with ui.tabs().classes('w-full') as tabs:
        tab_all = ui.tab('All Services')
        tab_public = ui.tab('Public')
        tab_internal = ui.tab('Internal')
    
    with ui.tab_panels(tabs, value=tab_all).classes('w-full'):
        with ui.tab_panel(tab_all):
            await render_services_table(services.values())
        
        with ui.tab_panel(tab_public):
            public_services = [s for s in services.values() if s.visibility == "public"]
            await render_services_table(public_services)
        
        with ui.tab_panel(tab_internal):
            internal_services = [s for s in services.values() if s.visibility == "internal"]
            await render_services_table(internal_services)


async def render_services_table(services):
    """Рендер таблицы сервисов"""
    columns = [
        {'name': 'status', 'label': '', 'field': 'status', 'align': 'center'},
        {'name': 'name', 'label': 'Name', 'field': 'name'},
        {'name': 'version', 'label': 'Version', 'field': 'version'},
        {'name': 'visibility', 'label': 'Visibility', 'field': 'visibility'},
        {'name': 'routing', 'label': 'Routing', 'field': 'routing'},
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
        
        routing_info = []
        for route in service.routing:
            if route.type == 'domain':
                routing_info.append(f"🌐 {route.domain}")
            elif route.type == 'subfolder':
                routing_info.append(f"📁 {route.base_domain}{route.path}")
            elif route.type == 'port':
                routing_info.append(f"🔌 :{route.port}")
        
        rows.append({
            'status': status_icon,
            'name': service.display_name or service.name,
            'version': service.version,
            'visibility': '🌍' if service.visibility == 'public' else '🔒',
            'routing': ' | '.join(routing_info),
            'service_name': service.name  # для actions
        })
    
    table = ui.table(columns=columns, rows=rows, row_key='name').classes('w-full')
    
    # Кастомные слоты для actions
    table.add_slot('body-cell-actions', '''
        <q-td :props="props">
            <q-btn flat dense icon="visibility" 
                   @click="$parent.$emit('view', props.row)" />
            <q-btn flat dense icon="restart_alt" 
                   @click="$parent.$emit('restart', props.row)" />
            <q-btn flat dense icon="stop" color="negative"
                   @click="$parent.$emit('stop', props.row)" />
        </q-td>
    ''')
    
    table.on('view', lambda e: ui.navigate.to(f'/services/{e.args["service_name"]}'))
    table.on('restart', lambda e: handle_restart(e.args["service_name"]))
    table.on('stop', lambda e: handle_stop(e.args["service_name"]))


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
            ui.notify(f'Failed: {result["message"]}', type='negative')


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
            ui.notify(f'Failed: {result["message"]}', type='negative')