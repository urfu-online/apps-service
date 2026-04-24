"""Страница управления бэкапами Kopia (Phase 4)."""
import asyncio
import aiohttp
from datetime import datetime, timezone
from typing import List, Optional, Dict
import humanize
from nicegui import ui

from app.ui.components.base import create_header, create_empty_state
from app.utils.i18n import natural_time


class BackupsPage:
    """Класс страницы управления бэкапами с polling и уведомлениями."""

    def __init__(self):
        self.backups_container: Optional[ui.column] = None
        self.settings_container: Optional[ui.column] = None
        self.service_select: Optional[ui.select] = None
        self.status_filter: Optional[ui.select] = None
        self.current_backups: List[Dict] = []
        self.selected_service: Optional[str] = None
        self.polling_task: Optional[asyncio.Task] = None
        self.polling_interval = 5  # секунды
        self.loading = False
        self.api_base = "/api/backups"
        # Сохранение настроек для предотвращения сброса при рендере
        self._retention_days_value: int = 7
        self._keep_daily_value: int = 7
        self._keep_weekly_value: int = 4
        self._keep_monthly_value: int = 12

    async def render(self):
        """Рендер страницы бэкапов."""
        from app.main import app

        # Заголовок с кнопкой обновления
        create_header(title='Бэкапы', show_refresh=True, on_refresh=lambda: self._refresh())

        # Панель управления
        with ui.card().classes('w-full px-6 mt-4').props('flat'):
            with ui.row().classes('w-full gap-4 items-end'):
                # Выбор сервиса
                services = list(app.state.discovery.services.keys())
                self.service_select = ui.select(
                    options=services,
                    label='Сервис',
                    on_change=self._on_service_change
                ).props('outlined dense').classes('flex-1')

                # Фильтр по статусу
                self.status_filter = ui.select(
                    options=[
                        {'label': 'Все статусы', 'value': ''},
                        {'label': '🟢 Успешно', 'value': 'created'},
                        {'label': '🟡 В процессе', 'value': 'uploading'},
                        {'label': '🔴 Ошибка', 'value': 'failed'},
                    ],
                    label='Статус'
                ).props('outlined dense').classes('w-40')

                # Кнопки действий
                with ui.row().classes('gap-2'):
                    ui.button(
                        'Обновить',
                        icon='refresh',
                        on_click=lambda: self._load_backups(force=True)
                    ).props('unelevated')

                    ui.button(
                        'Создать бэкап',
                        icon='add_circle',
                        on_click=lambda: self._create_backup_dialog()
                    ).props('unelevated color=primary')

        # Вкладки: Бэкапы и Настройки
        with ui.card().classes('w-full px-6 mt-4').props('flat bordered'):
            with ui.tabs().classes('w-full') as tabs:
                tab_backups = ui.tab('Бэкапы')
                tab_settings = ui.tab('Настройки')

            with ui.tab_panels(tabs, value=tab_backups).classes('w-full'):
                # Вкладка Бэкапы
                with ui.tab_panel(tab_backups):
                    self.backups_container = ui.column().classes('w-full')
                    with self.backups_container:
                        create_empty_state(
                            icon='📦',
                            message='Выберите сервис для просмотра бэкапов'
                        )

                # Вкладка Настройки
                with ui.tab_panel(tab_settings):
                    self.settings_container = ui.column().classes('w-full')
                    with self.settings_container:
                        self._render_settings()

        # Запуск polling при выборе сервиса
        self.service_select.on('update:model-value', lambda: self._start_polling())

    async def _on_service_change(self):
        """Обработчик изменения выбранного сервиса."""
        self.selected_service = self.service_select.value
        if self.selected_service:
            await self._load_backups()
            self._start_polling()
        else:
            self._stop_polling()
            self._clear_backups_table()

    def _clear_backups_table(self):
        """Очистка таблицы бэкапов."""
        if self.backups_container:
            self.backups_container.clear()
            with self.backups_container:
                create_empty_state(
                    icon='📦',
                    message='Выберите сервис для просмотра бэкапов'
                )

    async def _load_backups(self, force: bool = False):
        """Загрузка списка бэкапов через API."""
        if not self.selected_service:
            return

        if self.loading and not force:
            return

        self.loading = True
        try:
            # Показываем спиннер
            self.backups_container.clear()
            with self.backups_container:
                ui.spinner(size='lg').classes('self-center my-8')

            async with aiohttp.ClientSession() as session:
                url = f"{self.api_base}/{self.selected_service}"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        snapshots = await resp.json()
                        self.current_backups = snapshots
                        self._render_backups_table()
                    else:
                        error = await resp.text()
                        ui.notify(f'Ошибка загрузки: {error}', type='negative')
                        self._show_error('Не удалось загрузить бэкапы')
        except aiohttp.ClientError as e:
            ui.notify(f'Сетевая ошибка: {e}', type='negative')
            self._show_error('Ошибка соединения')
        except Exception as e:
            ui.notify(f'Неизвестная ошибка: {e}', type='negative')
            self._show_error('Внутренняя ошибка')
        finally:
            self.loading = False

    def _render_backups_table(self):
        """Рендер таблицы бэкапов."""
        if not self.backups_container:
            return

        self.backups_container.clear()

        if not self.current_backups:
            create_empty_state(
                icon='📭',
                message=f'Нет бэкапов для {self.selected_service}',
                action_label='Создать бэкап',
                on_click=lambda: self._create_backup_dialog()
            )
            return

        # Применяем фильтр по статусу
        filtered = self.current_backups
        status_filter = self.status_filter.value
        if status_filter:
            filtered = [b for b in self.current_backups if b.get('status') == status_filter]

        if not filtered:
            create_empty_state(
                icon='🔍',
                message='Нет бэкапов с выбранным статусом',
                action_label='Сбросить фильтр',
                on_click=lambda: self.status_filter.set_value('')
            )
            return

        # Заголовок таблицы
        ui.label(f'Бэкапы: {self.selected_service} ({len(filtered)} из {len(self.current_backups)})') \
            .classes('text-h6 mb-4')

        # Колонки таблицы с сортировкой
        columns = [
            {'name': 'snapshot_id', 'label': 'ID', 'field': 'snapshot_id', 'align': 'left', 'style': 'width: 100px', 'sortable': True},
            {'name': 'created_at', 'label': 'Создан', 'field': 'created_at', 'align': 'left', 'sortable': True, 'sort': 'desc'},
            {'name': 'status', 'label': 'Статус', 'field': 'status', 'align': 'center', 'style': 'width: 80px', 'sortable': True},
            {'name': 'size', 'label': 'Размер', 'field': 'size', 'align': 'right', 'sortable': True},
            {'name': 'retention_days', 'label': 'Хранение', 'field': 'retention_days', 'align': 'center', 'sortable': True},
            {'name': 'actions', 'label': 'Действия', 'field': 'actions', 'align': 'center', 'style': 'width: 150px'},
        ]

        # Подготовка строк
        rows = []
        for backup in filtered:
            snapshot_id = backup.get('snapshot_id', '')
            # Безопасное сокращение snapshot_id
            display_id = snapshot_id[:8] + '...' if len(snapshot_id) > 8 else snapshot_id
            rows.append({
                'snapshot_id': display_id,
                'created_at': self._format_datetime(backup['created_at']),
                'status': self._get_status_emoji(backup['status']),
                'size': self._format_size(backup.get('size_bytes')),
                'retention_days': f"{backup.get('retention_days', 7)} дн.",
                'snapshot_id_full': snapshot_id,  # Только ID, а не все данные
            })

        table = ui.table(
            columns=columns,
            rows=rows,
            row_key='snapshot_id'
        ).classes('w-full').props('flat bordered').props(
            'pagination-label="Строк на странице" pagination-rows-per-page-options="5,10,20,50" '
            'pagination-rows-per-page=10'
        )

        # Слот для статуса с тултипом
        table.add_slot('body-cell-status', '''
            <q-td :props="props">
                <q-tooltip>
                    {{ props.row.backup_data.status }}
                </q-tooltip>
                <div style="font-size: 1.5em;">
                    {{ props.row.status }}
                </div>
            </q-td>
        ''')

        # Слот для размера с тултипом точного значения
        table.add_slot('body-cell-size', '''
            <q-td :props="props">
                <q-tooltip>
                    {{ props.row.backup_data.size_bytes }} байт
                </q-tooltip>
                {{ props.row.size }}
            </q-td>
        ''')

        # Слот для действий
        table.add_slot('body-cell-actions', '''
            <q-td :props="props">
                <div class="row q-gutter-xs justify-center">
                    <q-btn flat dense round icon="restore" 
                           @click="$parent.$emit('restore', props.row.backup_data)" 
                           color="primary"
                           tooltip="Восстановить" />
                    <q-btn flat dense round icon="delete" 
                           @click="$parent.$emit('delete', props.row.backup_data)" 
                           color="negative"
                           tooltip="Удалить" />
                </div>
            </q-td>
        ''')

        # Обработчики событий
        table.on('restore', lambda e: self._restore_backup_dialog(e.args))
        table.on('delete', lambda e: self._delete_backup_dialog(e.args))

    def _format_datetime(self, dt_str: str) -> str:
        """Форматирование даты и времени."""
        try:
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return natural_time(dt)
        except (ValueError, AttributeError):
            return dt_str

    def _format_size(self, size_bytes: Optional[int]) -> str:
        """Форматирование размера с помощью humanize."""
        if size_bytes is None:
            return '—'
        return humanize.naturalsize(size_bytes, binary=True)

    def _get_status_emoji(self, status: str) -> str:
        """Получение эмодзи по статусу."""
        emoji_map = {
            'created': '🟢',
            'uploaded': '🟢',
            'uploading': '🟡',
            'failed': '🔴',
            'deleted': '⚫',
        }
        return emoji_map.get(status, '⚪')

    def _show_error(self, message: str):
        """Отображение состояния ошибки."""
        if self.backups_container:
            self.backups_container.clear()
            with self.backups_container:
                create_empty_state(
                    icon='❌',
                    message=message,
                    action_label='Повторить',
                    on_click=lambda: self._load_backups(force=True)
                )

    def _start_polling(self):
        """Запуск периодического обновления данных."""
        self._stop_polling()
        if self.selected_service:
            self.polling_task = asyncio.create_task(self._polling_loop())

    def _stop_polling(self):
        """Остановка polling."""
        if self.polling_task and not self.polling_task.done():
            self.polling_task.cancel()
            self.polling_task = None

    async def _polling_loop(self):
        """Цикл периодического обновления."""
        while True:
            try:
                await asyncio.sleep(self.polling_interval)
                await self._load_backups()
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Логируем ошибку, но продолжаем polling
                import logging
                logging.getLogger(__name__).error(f'Polling error: {e}')

    async def _refresh(self):
        """Ручное обновление."""
        if self.selected_service:
            await self._load_backups(force=True)
        else:
            ui.notify('Выберите сервис для обновления', type='info')

    # Диалоговые окна
    async def _create_backup_dialog(self):
        """Диалог создания бэкапа."""
        if not self.selected_service:
            ui.notify('Выберите сервис', type='warning')
            return

        with ui.dialog() as dialog, ui.card().classes('p-6 w-96'):
            ui.label('Создание бэкапа').classes('text-h6 mb-4')
            ui.label(f'Сервис: {self.selected_service}').classes('mb-4')

            reason_input = ui.input('Комментарий (необязательно)').props('outlined')

            with ui.row().classes('justify-end gap-2 mt-4'):
                ui.button('Отмена', on_click=dialog.close).props('flat')
                ui.button('Создать', on_click=lambda: self._create_backup(reason_input.value, dialog)) \
                    .props('unelevated color=primary')

        dialog.open()

    async def _create_backup(self, reason: str, dialog):
        """Отправка запроса на создание бэкапа."""
        dialog.close()
        ui.notify('Создание бэкапа...', type='info', timeout=None)

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_base}/{self.selected_service}/backup"
                payload = {'dry_run': False, 'reason': reason or 'manual'}
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        ui.notify(f'Бэкап создан: {result.get("snapshot_id", "—")}', type='positive')
                        await self._load_backups(force=True)
                    else:
                        error = await resp.text()
                        ui.notify(f'Ошибка: {error}', type='negative')
        except Exception as e:
            ui.notify(f'Ошибка: {e}', type='negative')

    async def _restore_backup_dialog(self, backup_data: Dict):
        """Диалог восстановления бэкапа с выбором целевой директории."""
        snapshot_id = backup_data['snapshot_id']
        service_name = backup_data['service_name']

        with ui.dialog() as dialog, ui.card().classes('p-6 w-96'):
            ui.label('Восстановление бэкапа').classes('text-h6 mb-4')
            ui.label(f'Сервис: {service_name}').classes('mb-2')
            ui.label(f'Снапшот: {snapshot_id[:12]}...').classes('mb-4')

            ui.label('Целевая директория (опционально)').classes('mb-2')
            target_input = ui.input(placeholder='/path/to/restore').props('outlined')

            ui.label('⚠️ Текущие данные будут заменены!', color='negative').classes('mb-4')

            with ui.row().classes('justify-end gap-2 mt-4'):
                ui.button('Отмена', on_click=dialog.close).props('flat')
                ui.button('Восстановить', on_click=lambda: self._restore_backup(
                    service_name, snapshot_id, target_input.value, dialog
                )).props('unelevated color=warning')

        dialog.open()

    async def _restore_backup(self, service_name: str, snapshot_id: str, target: str, dialog):
        """Отправка запроса на восстановление."""
        dialog.close()
        ui.notify('Восстановление...', type='info', timeout=None)

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_base}/{service_name}/restore/{snapshot_id}"
                payload = {'target': target if target else None, 'force': False}
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        ui.notify(f'Восстановление завершено: {result.get("message", "—")}', type='positive')
                        await self._load_backups(force=True)
                    else:
                        error = await resp.text()
                        ui.notify(f'Ошибка: {error}', type='negative')
        except Exception as e:
            ui.notify(f'Ошибка: {e}', type='negative')

    async def _delete_backup_dialog(self, backup_data: Dict):
        """Диалог подтверждения удаления бэкапа."""
        snapshot_id = backup_data['snapshot_id']

        with ui.dialog() as dialog, ui.card().classes('p-6 w-96'):
            ui.label('Удаление бэкапа').classes('text-h6 mb-4')
            ui.label(f'Снапшот: {snapshot_id[:12]}...').classes('mb-2')
            ui.label('Вы уверены? Это действие нельзя отменить.', color='negative').classes('mb-4')

            with ui.row().classes('justify-end gap-2 mt-4'):
                ui.button('Отмена', on_click=dialog.close).props('flat')
                ui.button('Удалить', on_click=lambda: self._delete_backup(snapshot_id, dialog)) \
                    .props('unelevated color=negative')

        dialog.open()

    async def _delete_backup(self, snapshot_id: str, dialog):
        """Отправка запроса на удаление."""
        dialog.close()
        ui.notify('Удаление...', type='info', timeout=None)

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_base}/snapshot/{snapshot_id}"
                async with session.delete(url) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        ui.notify(f'Удалено: {result.get("message", "—")}', type='positive')
                        await self._load_backups(force=True)
                    else:
                        error = await resp.text()
                        ui.notify(f'Ошибка: {error}', type='negative')
        except Exception as e:
            ui.notify(f'Ошибка: {e}', type='negative')

    def _render_settings(self):
        """Рендер вкладки настроек retention политик."""
        with self.settings_container:
            ui.label('Политики хранения').classes('text-h6 mb-4')
            ui.label('Настройте правила хранения снапшотов Kopia.').classes('text-body2 mb-6')

            with ui.card().classes('p-4 mb-4'):
                ui.label('Общие настройки').classes('text-subtitle1 mb-3')
                with ui.row().classes('w-full gap-4'):
                    self.retention_days_input = ui.number(
                        label='Дней хранения',
                        min=1,
                        max=3650,
                        value=self._retention_days_value,
                        format='%.0f'
                    ).props('outlined dense').classes('flex-1')
                    self.keep_daily_input = ui.number(
                        label='Ежедневных копий',
                        min=1,
                        max=100,
                        value=self._keep_daily_value,
                        format='%.0f'
                    ).props('outlined dense').classes('flex-1')
                with ui.row().classes('w-full gap-4 mt-2'):
                    self.keep_weekly_input = ui.number(
                        label='Еженедельных копий',
                        min=1,
                        max=52,
                        value=self._keep_weekly_value,
                        format='%.0f'
                    ).props('outlined dense').classes('flex-1')
                    self.keep_monthly_input = ui.number(
                        label='Ежемесячных копий',
                        min=1,
                        max=120,
                        value=self._keep_monthly_value,
                        format='%.0f'
                    ).props('outlined dense').classes('flex-1')

            with ui.card().classes('p-4'):
                ui.label('Применить к сервису').classes('text-subtitle1 mb-3')
                with ui.row().classes('w-full gap-4 items-end'):
                    from app.main import app
                    services = list(app.state.discovery.services.keys())
                    self.policy_service_select = ui.select(
                        options=services,
                        label='Сервис',
                        value=None
                    ).props('outlined dense').classes('flex-1')
                    ui.button(
                        'Применить политику',
                        icon='policy',
                        on_click=lambda: self._apply_retention_policy(
                            self.policy_service_select.value,
                            self.retention_days_input.value,
                            self.keep_daily_input.value,
                            self.keep_weekly_input.value,
                            self.keep_monthly_input.value
                        )
                    ).props('unelevated color=primary')

            ui.separator().classes('my-6')

            with ui.card().classes('p-4'):
                ui.label('Информация').classes('text-subtitle1 mb-3')
                ui.label('''Политики хранения определяют, как долго хранить снапшоты.
• Дней хранения: удалять снапшоты старше указанного количества дней.
• Ежедневные/еженедельные/ежемесячные копии: сохранять указанное количество последних снапшотов каждого периода.
Применение политики запустит задание очистки (enforce retention) для выбранного сервиса.''').classes('text-body2')

    async def _apply_retention_policy(self, service_name: str, retention_days: int,
                                      keep_daily: int, keep_weekly: int, keep_monthly: int):
        """Применить политику хранения к сервису."""
        if not service_name:
            ui.notify('Выберите сервис', type='warning')
            return

        # Сохраняем значения для предотвращения сброса
        self._retention_days_value = retention_days
        self._keep_daily_value = keep_daily
        self._keep_weekly_value = keep_weekly
        self._keep_monthly_value = keep_monthly

        ui.notify(f'Применение политики к {service_name}...', type='info', timeout=None)

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_base}/{service_name}/retention"
                payload = {
                    "retention_days": retention_days,
                    "keep_daily": keep_daily,
                    "keep_weekly": keep_weekly,
                    "keep_monthly": keep_monthly,
                }
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        ui.notify(f'Политика применена: {result.get("message", "")}', type='positive')
                    else:
                        error = await resp.text()
                        ui.notify(f'Ошибка: {error}', type='negative')
        except Exception as e:
            ui.notify(f'Ошибка: {e}', type='negative')


async def render_backups_page():
    """Рендер страницы бэкапов."""
    page = BackupsPage()
    await page.render()