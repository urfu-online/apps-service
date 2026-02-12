from nicegui import ui
from typing import List
from app.services.discovery import ServiceManifest


def create_service_card(service: ServiceManifest) -> ui.card:
    """Создание карточки сервиса"""
    with ui.card().classes('w-full') as card:
        # Заголовок карточки
        with ui.row().classes('w-full items-center'):
            status_icon = {
                'running': '🟢',
                'stopped': '🔴',
                'partial': '🟡',
                'unknown': '⚪'
            }.get(service.status, '⚪')
            
            ui.label(f"{status_icon} {service.display_name or service.name}").classes('text-h6')
            ui.space()
            
            # Теги видимости и типа
            ui.chip(f"{service.visibility}", icon='visibility').classes(
                'bg-green' if service.visibility == 'public' else 'bg-blue'
            )
            ui.chip(f"{service.type}", icon='category').classes('bg-purple')
        
        # Описание
        if service.description:
            ui.label(service.description).classes('text-subtitle2')
        
        # Версия
        ui.label(f"Version: {service.version}").classes('text-caption')
        
        # Маршрутизация
        routing_info = []
        for route in service.routing:
            if route.type == 'domain':
                routing_info.append(f"🌐 {route.domain}")
            elif route.type == 'subfolder':
                routing_info.append(f"📁 {route.base_domain}{route.path}")
            elif route.type == 'port':
                routing_info.append(f"🔌 :{route.port}")
        
        if routing_info:
            ui.label("Routing: " + " | ".join(routing_info)).classes('text-caption')
        
        # Кнопки действий
        with ui.row().classes('w-full justify-end'):
            ui.button('View', icon='visibility', 
                     on_click=lambda: ui.navigate.to(f'/services/{service.name}')).classes('mr-2')
            
            if service.status in ['stopped', 'unknown']:
                ui.button('Deploy', icon='play_arrow', 
                         on_click=lambda: handle_deploy(service.name)).classes('mr-2')
            else:
                ui.button('Restart', icon='restart_alt', 
                         on_click=lambda: handle_restart(service.name)).classes('mr-2')
                ui.button('Stop', icon='stop', 
                         on_click=lambda: handle_stop(service.name)).classes('mr-2')
    
    return card


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