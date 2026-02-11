from nicegui import ui
from datetime import datetime
from typing import List


async def render_backups_page():
    """Рендер страницы бэкапов"""
    from app.main import app
    
    # Заголовок
    with ui.row().classes('w-full items-center'):
        ui.label('Backups').classes('text-h4')
        ui.space()
        ui.button('Refresh', on_click=lambda: ui.navigate.reload()).classes('ml-auto')
    
    # Фильтры
    with ui.row().classes('w-full items-center'):
        service_select = ui.select(
            options=list(app.state.discovery.services.keys()),
            label='Service'
        ).classes('mr-2')
        
        ui.button('Show Backups', on_click=lambda: show_service_backups(
            service_select.value
        )).classes('mr-2')
        
        ui.button('Create Backup', on_click=lambda: create_backup(
            service_select.value
        )).classes('mr-2')
    
    # Область отображения бэкапов
    with ui.card().classes('w-full'):
        ui.label('Select a service to view backups').classes('text-center')


async def show_service_backups(service_name: str):
    """Отображение бэкапов сервиса"""
    from app.main import app
    
    if not service_name:
        ui.notify('Please select a service', type='warning')
        return
    
    # Получаем сервис
    service = app.state.discovery.get_service(service_name)
    if not service:
        ui.notify(f'Service {service_name} not found', type='negative')
        return
    
    # Получаем бэкапы
    backups = await app.state.backup.list_backups(service)
    
    # Очищаем текущее содержимое
    for element in ui.context.client.elements.values():
        if hasattr(element, 'tag') and element.tag == 'div' and 'backup-list' in str(element.classes):
            element.delete()
    
    # Создаем новую область для бэкапов
    with ui.column().classes('w-full backup-list'):
        ui.label(f'Backups for {service_name}').classes('text-h6')
        
        if not backups:
            ui.label('No backups found').classes('text-center')
            return
        
        # Создаем таблицу бэкапов
        columns = [
            {'name': 'name', 'label': 'Name', 'field': 'name'},
            {'name': 'timestamp', 'label': 'Timestamp', 'field': 'timestamp'},
            {'name': 'reason', 'label': 'Reason', 'field': 'reason'},
            {'name': 'actions', 'label': 'Actions', 'field': 'actions'},
        ]
        
        rows = []
        for backup in backups:
            rows.append({
                'name': backup.get('backup_name', ''),
                'timestamp': backup.get('timestamp', ''),
                'reason': backup.get('reason', ''),
                'backup_data': backup  # Для использования в действиях
            })
        
        table = ui.table(columns=columns, rows=rows, row_key='name').classes('w-full')
        
        # Кастомные слоты для actions
        table.add_slot('body-cell-actions', '''
            <q-td :props="props">
                <q-btn flat dense icon="restore" 
                       @click="$parent.$emit('restore', props.row)" />
                <q-btn flat dense icon="delete" color="negative"
                       @click="$parent.$emit('delete', props.row)" />
            </q-td>
        ''')
        
        table.on('restore', lambda e: handle_restore_backup(e.args["backup_data"]))
        table.on('delete', lambda e: handle_delete_backup(e.args["backup_data"]))


async def create_backup(service_name: str):
    """Создание бэкапа сервиса"""
    from app.main import app
    
    if not service_name:
        ui.notify('Please select a service', type='warning')
        return
    
    # Получаем сервис
    service = app.state.discovery.get_service(service_name)
    if not service:
        ui.notify(f'Service {service_name} not found', type='negative')
        return
    
    # Создаем бэкап
    ui.notify(f'Creating backup for {service_name}...', type='info')
    result = await app.state.backup.backup_service(service, reason="manual")
    
    if result['success']:
        ui.notify(f'Backup created: {result["backup_name"]}', type='positive')
        # Обновляем отображение
        await show_service_backups(service_name)
    else:
        ui.notify(f'Backup failed: {result["errors"][0] if result["errors"] else "Unknown error"}', type='negative')


async def handle_restore_backup(backup_data: dict):
    """Обработка восстановления бэкапа"""
    backup_name = backup_data.get('backup_name', '')
    ui.notify(f'Restore scheduled for {backup_name}', type='info')


async def handle_delete_backup(backup_data: dict):
    """Обработка удаления бэкапа"""
    backup_name = backup_data.get('backup_name', '')
    ui.notify(f'Deletion scheduled for {backup_name}', type='info')