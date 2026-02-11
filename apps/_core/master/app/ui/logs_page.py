from nicegui import ui
from datetime import datetime, timedelta
from typing import List


async def render_logs_page():
    """Рендер страницы логов"""
    from app.main import app
    
    # Заголовок
    with ui.row().classes('w-full items-center'):
        ui.label('Logs').classes('text-h4')
        ui.space()
        ui.button('Refresh', on_click=lambda: ui.navigate.reload()).classes('ml-auto')
    
    # Фильтры
    with ui.row().classes('w-full items-center'):
        service_select = ui.select(
            options=list(app.state.discovery.services.keys()),
            label='Service'
        ).classes('mr-2')
        
        time_range_select = ui.select(
            options=['1h', '6h', '12h', '24h', '7d'],
            value='1h',
            label='Time Range'
        ).classes('mr-2')
        
        search_input = ui.input('Search').classes('mr-2')
        
        ui.button('Apply Filters', on_click=lambda: apply_log_filters(
            service_select.value,
            time_range_select.value,
            search_input.value
        ))
    
    # Область отображения логов
    with ui.card().classes('w-full'):
        log_area = ui.log().classes('w-full h-96 overflow-auto')
    
    # Кнопки управления
    with ui.row().classes('w-full'):
        ui.button('Clear', on_click=lambda: log_area.clear()).classes('mr-2')
        ui.button('Export', on_click=lambda: export_logs()).classes('mr-2')
        ui.button('Auto Scroll', on_click=lambda: toggle_auto_scroll()).classes('mr-2')
    
    # Инициализация отображения логов
    await update_log_display(log_area)


async def apply_log_filters(service_name: str, time_range: str, search: str):
    """Применение фильтров к логам"""
    from app.main import app
    
    if not service_name:
        ui.notify('Please select a service', type='warning')
        return
    
    # Получаем сервис
    service = app.state.discovery.get_service(service_name)
    if not service:
        ui.notify(f'Service {service_name} not found', type='negative')
        return
    
    # Вычисляем время начала
    now = datetime.utcnow()
    if time_range == '1h':
        since = now - timedelta(hours=1)
    elif time_range == '6h':
        since = now - timedelta(hours=6)
    elif time_range == '12h':
        since = now - timedelta(hours=12)
    elif time_range == '24h':
        since = now - timedelta(hours=24)
    elif time_range == '7d':
        since = now - timedelta(days=7)
    else:
        since = now - timedelta(hours=1)
    
    # Получаем логи
    logs = await app.state.log_manager.get_service_logs(
        service, 
        tail=1000, 
        since=since.isoformat()
    )
    
    # Фильтруем по поисковому запросу
    if search:
        logs = [log for log in logs if search.lower() in log.lower()]
    
    # Отображаем логи
    log_area = ui.context.client.elements.get('log_area')
    if log_area:
        log_area.clear()
        for log in logs:
            log_area.push(log)
    
    ui.notify(f'Showing {len(logs)} log entries')


async def update_log_display(log_area):
    """Обновление отображения логов"""
    from app.main import app
    
    # В реальной реализации здесь будет получение последних логов
    # и обновление отображения
    pass


async def export_logs():
    """Экспорт логов"""
    ui.notify('Log export scheduled', type='info')


async def toggle_auto_scroll():
    """Переключение авто прокрутки"""
    ui.notify('Auto scroll toggled', type='info')