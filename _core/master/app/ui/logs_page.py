"""Страница просмотра логов."""
import asyncio
from nicegui import ui
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from app.ui.components.base import (
    create_header,
)
from app.utils.i18n import natural_delta


class LogsPage:
    """Класс страницы просмотра логов."""

    TIME_RANGES = {
        '1h': timedelta(hours=1),
        '6h': timedelta(hours=6),
        '12h': timedelta(hours=12),
        '24h': timedelta(hours=24),
        '7d': timedelta(days=7),
    }

    def __init__(self):
        self.log_area: Optional[ui.log] = None
        self.service_select: Optional[ui.select] = None
        self.time_range_select: Optional[ui.select] = None
        self.search_input: Optional[ui.input] = None
        self.auto_scroll: bool = True
        self.logs_cache: List[str] = []
        # Phase 4: Loading, export, and auto-refresh
        self.loading: bool = False
        self.loading_spinner: Optional[ui.spinner] = None
        self.auto_refresh: bool = False
        self.refresh_interval: int = 5  # seconds
        self.refresh_timer: Optional[asyncio.Task] = None
        self.export_button: Optional[ui.button] = None
        self.auto_refresh_toggle: Optional[ui.toggle] = None

    async def render(self):
        """Рендер страницы логов."""
        from app.main import app

        # Заголовок
        create_header(title='Логи', show_refresh=True, on_refresh=lambda: self._load_logs())

        # Панель фильтров
        with ui.card().classes('w-full px-6 mt-4').props('flat'):
            with ui.row().classes('w-full gap-4 items-end'):
                # Выбор сервиса
                services = list(app.state.discovery.services.keys())
                self.service_select = ui.select(
                    options=services,
                    label='Сервис',
                    on_change=lambda _: self._load_logs()
                ).props('outlined dense').classes('flex-1')

                # Период времени
                self.time_range_select = ui.select(
                    options={
                        '1h': '1 час',
                        '6h': '6 часов',
                        '12h': '12 часов',
                        '24h': '24 часа',
                        '7d': '7 дней',
                    },
                    value='1h',
                    label='Период',
                    on_change=lambda _: self._load_logs()
                ).props('outlined dense').classes('w-40')

                # Поиск
                self.search_input = ui.input(
                    label='Поиск',
                    placeholder='Текст в логах',
                    on_change=lambda _: self._filter_logs()
                ).props('outlined dense').classes('flex-1')

                # Кнопки управления
                with ui.row().classes('gap-2'):
                    # Phase 4: Loading spinner
                    self.loading_spinner = ui.spinner(size='sm').classes('hidden')
                    
                    ui.button('Загрузить', icon='refresh', on_click=lambda: self._load_logs()) \
                        .props('unelevated')
                    ui.button('Очистить', icon='clear', on_click=lambda: self._clear_logs()) \
                        .props('flat')
                    
                    # Phase 4: Export button
                    self.export_button = ui.button('Экспорт', icon='download', on_click=lambda: self._export_logs()) \
                        .props('flat')
                    
                    # Phase 4: Auto-refresh toggle
                    self.auto_refresh_toggle = ui.toggle(
                        {False: 'Авто', True: 'Авто'},
                        value=False,
                        on_change=lambda e: self._toggle_auto_refresh(e.value)
                    ).props('dense flat round').classes('w-20')
                    
                    ui.button(icon='arrow_downward', on_click=self._toggle_auto_scroll) \
                        .props('flat round').tooltip('Автопрокрутка')

        # Область логов
        with ui.card().classes('w-full px-6 mt-4').props('flat bordered'):
            self.log_container = ui.column().classes('w-full')
            with self.log_container:
                self.log_area = ui.log().classes('w-full h-[500px] font-mono text-sm bg-grey-1 rounded')

        # Статистика
        with ui.row().classes('w-full px-6 mt-2'):
            self.status_label = ui.label('Выберите сервис для просмотра логов').classes('text-caption text-grey-7')
            self.period_label = ui.label('').classes('text-caption text-grey-7 ml-4')

    def _get_since_time(self, range_key: str) -> datetime:
        """Вычисление времени начала периода."""
        delta = self.TIME_RANGES.get(range_key, timedelta(hours=1))
        return datetime.now(timezone.utc) - delta

    async def _load_logs(self):
        """Загрузка логов."""
        from app.main import app

        if not self.log_area:
            return

        service_name = self.service_select.value if self.service_select else None
        if not service_name:
            ui.notify('Выберите сервис', type='warning')
            return

        service = app.state.discovery.get_service(service_name)
        if not service:
            ui.notify(f'Сервис {service_name} не найден', type='negative')
            return

        # Phase 4: Show loading spinner
        self.loading = True
        if self.loading_spinner:
            self.loading_spinner.classes.remove('hidden')
        if self.export_button:
            self.export_button.props('disable')
        
        # Получаем период
        time_range = self.time_range_select.value if self.time_range_select else '1h'
        since = self._get_since_time(time_range)

        try:
            logs = await app.state.log_manager.get_service_logs(
                service,
                tail=1000,
                since=since.isoformat()
            )
            self.logs_cache = logs

            # Отображаем
            self._display_logs()

            self.status_label.set_text(f'Загружено {len(logs)} записей')
            self.period_label.set_text(f'Период: {natural_delta(self.TIME_RANGES.get(time_range, timedelta(hours=1)))} назад')
        except Exception as e:
            ui.notify(f'Ошибка загрузки логов: {e}', type='negative')
            self.status_label.set_text('Ошибка загрузки')
        finally:
            # Phase 4: Hide loading spinner
            self.loading = False
            if self.loading_spinner:
                self.loading_spinner.classes.add('hidden')
            if self.export_button:
                self.export_button.props('remove', 'disable')

    async def _export_logs(self):
        """Экспорт логов через API."""
        from app.main import app
        import json

        service_name = self.service_select.value if self.service_select else None
        if not service_name:
            ui.notify('Выберите сервис для экспорта', type='warning')
            return

        try:
            # Call the export API endpoint
            async with app.state.http_client.get(
                f'/api/logs/service/{service_name}/export'
            ) as response:
                if response.status_code == 200:
                    # Get the file content and trigger download
                    content = await response.read()
                    # Create a blob and trigger download in browser
                    ui.notify('Экспорт логов завершён', type='positive')
                else:
                    error_text = await response.text()
                    ui.notify(f'Ошибка экспорта: {error_text}', type='negative')
        except Exception as e:
            ui.notify(f'Ошибка экспорта: {e}', type='negative')

    def _toggle_auto_refresh(self, enabled: bool):
        """Toggle auto-refresh polling."""
        self.auto_refresh = enabled
        
        if enabled:
            # Start the polling timer
            self._start_auto_refresh()
            ui.notify(f'Автообновление включено ({self.refresh_interval}с)', type='info', timeout=1500)
        else:
            # Stop the polling timer
            self._stop_auto_refresh()
            ui.notify('Автообновление выключено', type='info', timeout=1500)

    def _start_auto_refresh(self):
        """Start auto-refresh polling timer."""
        self._stop_auto_refresh()  # Ensure any existing timer is stopped
        
        async def poll():
            while self.auto_refresh:
                await self._load_logs()
                await asyncio.sleep(self.refresh_interval)
        
        self.refresh_timer = asyncio.create_task(poll())

    def _stop_auto_refresh(self):
        """Stop auto-refresh polling timer."""
        if self.refresh_timer:
            self.refresh_timer.cancel()
            self.refresh_timer = None

    def _display_logs(self):
        """Отображение логов."""
        if not self.log_area:
            return

        self.log_area.clear()
        
        search_term = (self.search_input.value or '').lower() if self.search_input else ''
        
        for log in self.logs_cache:
            # Фильтрация по поиску
            if search_term and search_term not in log.lower():
                continue
            
            # Форматирование
            formatted = self._format_log_entry(log)
            self.log_area.push(formatted)

    def _format_log_entry(self, log: str) -> str:
        """Форматирование записи лога."""
        # Определяем уровень лога
        log_lower = log.lower()
        prefix = '○'
        color_class = ''
        
        if 'error' in log_lower or 'exception' in log_lower or 'fatal' in log_lower:
            prefix = '✗'
            color_class = ' text-red'
        elif 'warning' in log_lower or 'warn' in log_lower:
            prefix = '!'
            color_class = ' text-yellow'
        elif 'debug' in log_lower:
            prefix = '⋯'
            color_class = ' text-grey'
        elif 'info' in log_lower:
            prefix = 'ℹ'
            color_class = ' text-blue'
        elif 'success' in log_lower or 'started' in log_lower or 'ready' in log_lower:
            prefix = '✓'
            color_class = ' text-green'

        return f'<span class="{color_class}">{prefix}</span> {log}'

    def _filter_logs(self):
        """Фильтрация логов по поиску."""
        self._display_logs()
        
        count = sum(1 for log in self.logs_cache 
                   if (self.search_input.value or '').lower() in log.lower())
        self.status_label.set_text(f'Найдено {count} из {len(self.logs_cache)}')

    def _clear_logs(self):
        """Очистка логов."""
        if self.log_area:
            self.log_area.clear()
        self.logs_cache = []
        self.status_label.set_text('Логи очищены')

    def _toggle_auto_scroll(self):
        """Переключение автопрокрутки."""
        self.auto_scroll = not self.auto_scroll
        ui.notify(
            f'Автопрокрутка {"включена" if self.auto_scroll else "выключена"}',
            type='info',
            timeout=1500
        )


async def render_logs_page():
    """Рендер страницы логов."""
    page = LogsPage()
    await page.render()
