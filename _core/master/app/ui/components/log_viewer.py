"""Компонент просмотра логов."""
from nicegui import ui
from datetime import datetime, timezone
from typing import List, Optional, Callable
from enum import Enum


class LogLevel(Enum):
    """Уровни логирования."""
    DEBUG = 'debug'
    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'
    SUCCESS = 'success'


class LogViewer(ui.column):
    """Компонент для просмотра и управления логами.
    
    Пример использования:
        viewer = LogViewer()
        viewer.add_log('Сервис запущен', LogLevel.INFO)
        viewer.add_log('Ошибка подключения', LogLevel.ERROR)
    """

    LEVEL_CONFIG = {
        LogLevel.DEBUG: {'icon': '🐛', 'color': 'grey', 'label': 'DEBUG'},
        LogLevel.INFO: {'icon': 'ℹ', 'color': 'blue', 'label': 'INFO'},
        LogLevel.WARNING: {'icon': '⚠', 'color': 'yellow', 'label': 'WARN'},
        LogLevel.ERROR: {'icon': '✗', 'color': 'red', 'label': 'ERROR'},
        LogLevel.SUCCESS: {'icon': '✓', 'color': 'green', 'label': 'SUCCESS'},
    }

    def __init__(self, height: str = 'h-96', max_lines: int = 1000,
                 show_toolbar: bool = True, auto_scroll: bool = True):
        """Инициализация просмотрщика логов.
        
        Args:
            height: Высота области логов (CSS класс)
            max_lines: Максимальное количество строк
            show_toolbar: Показывать панель управления
            auto_scroll: Автопрокрутка к новым записям
        """
        super().__init__()
        
        self._max_lines = max_lines
        self._auto_scroll = auto_scroll
        self._entries: List[str] = []
        
        self.classes('w-full')
        
        # Панель управления
        if show_toolbar:
            self._render_toolbar()
        
        # Область логов
        with self:
            self._log_area = ui.log().classes(f'w-full {height} font-mono text-sm bg-grey-1 rounded')

    def _render_toolbar(self):
        """Рендер панели управления."""
        with ui.row().classes('w-full items-center justify-between mb-2'):
            ui.label('Логи').classes('text-h6')
            
            with ui.row().classes('gap-2'):
                self._auto_scroll_btn = ui.button(
                    icon='arrow_downward',
                    on_click=self._toggle_auto_scroll
                ).props('flat dense round').tooltip('Автопрокрутка')
                
                ui.button(
                    icon='clear',
                    on_click=self.clear
                ).props('flat dense round').tooltip('Очистить')
                
                ui.button(
                    icon='download',
                    on_click=self._export
                ).props('flat dense round').tooltip('Экспорт')

    def add_log(self, message: str, level: LogLevel = LogLevel.INFO,
                timestamp: Optional[datetime] = None):
        """Добавление записи в лог.
        
        Args:
            message: Сообщение лога
            level: Уровень логирования
            timestamp: Временная метка (по умолчанию сейчас)
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        config = self.LEVEL_CONFIG.get(level, self.LEVEL_CONFIG[LogLevel.INFO])
        
        # Форматируем запись
        time_str = timestamp.strftime('%H:%M:%S')
        formatted = f'<span class="text-grey-5">[{time_str}]</span> ' \
                   f'<span class="text-{config["color"]}">{config["icon"]}</span> ' \
                   f'{self._escape_html(message)}'
        
        # Добавляем в лог
        self._log_area.push(formatted)
        self._entries.append(formatted)
        
        # Удаляем старые записи если превышен лимит
        if len(self._entries) > self._max_lines:
            self._entries = self._entries[-self._max_lines:]

    def add_logs(self, messages: List[str], level: LogLevel = LogLevel.INFO):
        """Добавление нескольких записей.
        
        Args:
            messages: Список сообщений
            level: Уровень логирования
        """
        for message in messages:
            self.add_log(message, level)

    def clear(self):
        """Очистка всех логов."""
        self._log_area.clear()
        self._entries = []

    def set_auto_scroll(self, enabled: bool):
        """Включение/отключение автопрокрутки.
        
        Args:
            enabled: Включить автопрокрутку
        """
        self._auto_scroll = enabled

    def _toggle_auto_scroll(self):
        """Переключатель автопрокрутки."""
        self._auto_scroll = not self._auto_scroll
        status = 'включена' if self._auto_scroll else 'выключена'
        ui.notify(f'Автопрокрутка {status}', type='info', timeout=1500)

    def _export(self):
        """Экспорт логов."""
        if not self._entries:
            ui.notify('Нет логов для экспорта', type='warning')
            return
        
        # Создаем текстовую версию для экспорта
        text_content = '\n'.join(self._strip_html(entry) for entry in self._entries)
        
        # В реальной реализации здесь будет скачивание файла
        ui.notify('Экспорт логов подготовлен', type='info')

    def _escape_html(self, text: str) -> str:
        """Экранирование HTML символов."""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;'))

    def _strip_html(self, html: str) -> str:
        """Удаление HTML тегов для экспорта."""
        import re
        return re.sub(r'<[^>]+>', '', html)

    @property
    def entries_count(self) -> int:
        """Количество записей в логе."""
        return len(self._entries)


def create_log_viewer(height: str = 'h-96', max_lines: int = 1000,
                      show_toolbar: bool = True, auto_scroll: bool = True) -> LogViewer:
    """Фабричная функция для создания просмотрщика логов.
    
    Args:
        height: Высота области логов
        max_lines: Максимальное количество строк
        show_toolbar: Показывать панель управления
        auto_scroll: Автопрокрутка к новым записям
        
    Returns:
        Экземпляр LogViewer
    """
    return LogViewer(
        height=height,
        max_lines=max_lines,
        show_toolbar=show_toolbar,
        auto_scroll=auto_scroll
    )
