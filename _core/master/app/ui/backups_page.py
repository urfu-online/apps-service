"""Страница управления бэкапами."""
from nicegui import ui
from datetime import datetime, timezone
from typing import List, Optional, Dict

from app.ui.components.base import (
    create_header,
    create_empty_state,
)
from app.utils.i18n import natural_time


class BackupsPage:
    """Класс страницы управления бэкапами."""

    def __init__(self):
        self.backups_container: Optional[ui.column] = None
        self.service_select: Optional[ui.select] = None
        self.current_backups: List[Dict] = []
        self.selected_backup: Optional[Dict] = None

    async def render(self):
        """Рендер страницы бэкапов."""
        from app.main import app

        # Заголовок
        create_header(title='Бэкапы', show_refresh=True, on_refresh=lambda: self._refresh())

        # Панель выбора сервиса
        with ui.card().classes('w-full px-6 mt-4').props('flat'):
            with ui.row().classes('w-full gap-4 items-end'):
                services = list(app.state.discovery.services.keys())
                self.service_select = ui.select(
                    options=services,
                    label='Сервис'
                ).props('outlined dense').classes('flex-1')

                with ui.row().classes('gap-2'):
                    ui.button(
                        'Показать бэкапы',
                        icon='folder_open',
                        on_click=lambda: self._load_backups()
                    ).props('unelevated')
                    
                    ui.button(
                        'Создать бэкап',
                        icon='add_circle',
                        on_click=lambda: self._create_backup()
                    ).props('unelevated color=primary')

        # Контейнер для списка бэкапов
        with ui.card().classes('w-full px-6 mt-4').props('flat bordered'):
            self.backups_container = ui.column().classes('w-full')
            with self.backups_container:
                create_empty_state(
                    icon='📦',
                    message='Выберите сервис для просмотра бэкапов'
                )

    async def _load_backups(self):
        """Загрузка списка бэкапов."""
        from app.main import app

        service_name = self.service_select.value
        if not service_name:
            ui.notify('Выберите сервис', type='warning')
            return

        service = app.state.discovery.get_service(service_name)
        if not service:
            ui.notify(f'Сервис {service_name} не найден', type='negative')
            return

        # Очищаем контейнер
        self.backups_container.clear()

        # Загружаем бэкапы
        ui.notify('Загрузка бэкапов...', type='info', timeout=1000)
        
        try:
            backups = await app.state.backup.list_backups(service)
            self.current_backups = backups or []

            if not self.current_backups:
                create_empty_state(
                    icon='📭',
                    message=f'Нет бэкапов для {service_name}',
                    action_label='Создать бэкап',
                    on_click=lambda: self._create_backup()
                )
                return

            # Заголовок списка
            ui.label(f'Бэкапы: {service_name} ({len(self.current_backups)})') \
                .classes('text-h6 mb-4')

            # Таблица бэкапов
            self._render_backups_table()

        except Exception as e:
            ui.notify(f'Ошибка загрузки: {e}', type='negative')
            create_empty_state(
                icon='❌',
                message='Ошибка загрузки бэкапов'
            )

    def _render_backups_table(self):
        """Рендер таблицы бэкапов."""
        columns = [
            {'name': 'name', 'label': 'Имя', 'field': 'name', 'align': 'left'},
            {'name': 'timestamp', 'label': 'Дата создания', 'field': 'timestamp', 'align': 'left'},
            {'name': 'reason', 'label': 'Причина', 'field': 'reason', 'align': 'left'},
            {'name': 'size', 'label': 'Размер', 'field': 'size', 'align': 'right'},
            {'name': 'actions', 'label': 'Действия', 'field': 'actions', 'align': 'center'},
        ]

        rows = []
        for backup in self.current_backups:
            rows.append({
                'name': backup.get('backup_name', '—'),
                'timestamp': self._format_timestamp(backup.get('timestamp', '')),
                'reason': backup.get('reason', '—') or '—',
                'size': backup.get('size', '—'),
                'backup_data': backup,
            })

        table = ui.table(
            columns=columns,
            rows=rows,
            row_key='name'
        ).classes('w-full').props('flat bordered')

        self._add_action_slots(table)
        self._add_table_events(table)

    def _format_timestamp(self, timestamp: str) -> str:
        """Форматирование временной метки."""
        if not timestamp:
            return '—'
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return natural_time(dt)
        except (ValueError, AttributeError):
            return str(timestamp)

    def _add_action_slots(self, table: ui.table):
        """Добавление слотов действий."""
        table.add_slot('body-cell-actions', '''
            <q-td :props="props">
                <div class="row q-gutter-xs justify-center">
                    <q-btn flat dense round icon="restore" 
                           @click="$parent.$emit('restore', props.row)" 
                           color="primary"
                           tooltip="Восстановить" />
                    <q-btn flat dense round icon="delete" 
                           @click="$parent.$emit('delete', props.row)" 
                           color="negative"
                           tooltip="Удалить" />
                </div>
            </q-td>
        ''')

    def _add_table_events(self, table: ui.table):
        """Добавление обработчиков событий."""
        table.on('restore', lambda e: self._handle_restore(e.args['backup_data']))
        table.on('delete', lambda e: self._handle_delete(e.args['backup_data']))

    async def _create_backup(self):
        """Создание нового бэкапа."""
        from app.main import app

        service_name = self.service_select.value
        if not service_name:
            ui.notify('Выберите сервис', type='warning')
            return

        service = app.state.discovery.get_service(service_name)
        if not service:
            ui.notify(f'Сервис {service_name} не найден', type='negative')
            return

        # Диалог подтверждения
        with ui.dialog() as dialog, ui.card().classes('p-6 w-96'):
            ui.label('Создание бэкапа').classes('text-h6 mb-4')
            ui.label(f'Сервис: {service_name}').classes('mb-4')
            
            reason_input = ui.input('Комментарий (необязательно)').props('outlined')
            
            with ui.row().classes('justify-end gap-2 mt-4'):
                ui.button('Отмена', on_click=dialog.close).props('flat')
                ui.button('Создать', on_click=lambda: self._confirm_backup(service, reason_input.value, dialog)) \
                    .props('unelevated color=primary')

        dialog.open()

    async def _confirm_backup(self, service, reason: str, dialog):
        """Подтверждение создания бэкапа."""
        from app.main import app

        dialog.close()
        ui.notify('Создание бэкапа...', type='info', timeout=None)

        try:
            result = await app.state.backup.backup_service(service, reason=reason or 'manual')

            if result.get('success'):
                ui.notify(f'Бэкап создан: {result.get("backup_name", "—")}', type='positive')
                await self._load_backups()  # Обновляем список
            else:
                errors = result.get('errors', ['Неизвестная ошибка'])
                ui.notify(f'Ошибка: {errors[0]}', type='negative')
        except Exception as e:
            ui.notify(f'Ошибка: {e}', type='negative')

    async def _handle_restore(self, backup_data: Dict):
        """Обработка восстановления из бэкапа."""
        backup_name = backup_data.get('backup_name', '')
        service_name = backup_data.get('service_name', 'сервис')

        with ui.dialog() as dialog, ui.card().classes('p-6 w-96'):
            ui.label('Восстановление из бэкапа').classes('text-h6 mb-4')
            ui.label(f'Бэкап: {backup_name}').classes('mb-2')
            ui.label('⚠️ Текущие данные будут заменены!', color='negative').classes('mb-4')
            
            with ui.row().classes('justify-end gap-2 mt-4'):
                ui.button('Отмена', on_click=dialog.close).props('flat')
                ui.button('Восстановить', on_click=lambda: self._confirm_restore(backup_data, dialog)) \
                    .props('unelevated color=warning')

        dialog.open()

    async def _confirm_restore(self, backup_data: Dict, dialog):
        """Подтверждение восстановления."""
        from app.main import app

        dialog.close()
        ui.notify('Восстановление...', type='info', timeout=None)

        # Здесь должна быть логика восстановления
        # await app.state.backup.restore_backup(backup_data)

        ui.notify('Функция восстановления в разработке', type='warning')

    async def _handle_delete(self, backup_data: Dict):
        """Обработка удаления бэкапа."""
        backup_name = backup_data.get('backup_name', '')

        with ui.dialog() as dialog, ui.card().classes('p-6 w-96'):
            ui.label('Удаление бэкапа').classes('text-h6 mb-4')
            ui.label(f'Бэкап: {backup_name}').classes('mb-2')
            ui.label('Вы уверены? Это действие нельзя отменить.', color='negative').classes('mb-4')
            
            with ui.row().classes('justify-end gap-2 mt-4'):
                ui.button('Отмена', on_click=dialog.close).props('flat')
                ui.button('Удалить', on_click=lambda: self._confirm_delete(backup_data, dialog)) \
                    .props('unelevated color=negative')

        dialog.open()

    async def _confirm_delete(self, backup_data: Dict, dialog):
        """Подтверждение удаления."""
        from app.main import app

        dialog.close()
        ui.notify('Удаление бэкапа...', type='info', timeout=None)

        # Здесь должна быть логика удаления
        # await app.state.backup.delete_backup(backup_data)

        ui.notify('Функция удаления в разработке', type='warning')

    async def _refresh(self):
        """Обновление страницы."""
        if self.service_select.value:
            await self._load_backups()
        else:
            ui.notify('Выберите сервис для обновления', type='info')


async def render_backups_page():
    """Рендер страницы бэкапов."""
    page = BackupsPage()
    await page.render()
