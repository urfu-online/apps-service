from nicegui import ui
from datetime import datetime, timedelta
from typing import List


class LogViewer:
    """Компонент просмотра логов"""
    
    def __init__(self):
        self.log_area = None
        self.auto_scroll = True
        self.max_lines = 1000
    
    def create(self, height: str = 'h-96') -> ui.log:
        """Создание компонента просмотра логов"""
        with ui.card().classes('w-full'):
            # Панель управления
            with ui.row().classes('w-full items-center'):
                ui.label('Logs').classes('text-h6')
                ui.space()
                ui.button('Clear', icon='clear', on_click=self.clear).classes('mr-2')
                ui.button('Export', icon='download', on_click=self.export).classes('mr-2')
                self.auto_scroll_checkbox = ui.checkbox('Auto Scroll', value=True, 
                                                       on_change=self.toggle_auto_scroll).classes('mr-2')
            
            # Область отображения логов
            self.log_area = ui.log().classes(f'w-full {height} overflow-auto')
        
        return self.log_area
    
    def add_log(self, message: str, level: str = 'info'):
        """Добавление записи в лог"""
        if not self.log_area:
            return
        
        # Форматируем сообщение с учетом уровня
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        level_icon = {
            'error': '❌',
            'warning': '⚠️',
            'info': 'ℹ️',
            'debug': '🐛'
        }.get(level, 'ℹ️')
        
        formatted_message = f"[{timestamp}] {level_icon} {message}"
        
        # Добавляем сообщение в лог
        self.log_area.push(formatted_message)
        
        # Прокручиваем вниз, если включена авто прокрутка
        if self.auto_scroll:
            # В NiceGUI автоматическая прокрутка происходит при добавлении сообщений
            pass
    
    def clear(self):
        """Очистка логов"""
        if self.log_area:
            self.log_area.clear()
    
    def toggle_auto_scroll(self):
        """Переключение авто прокрутки"""
        self.auto_scroll = self.auto_scroll_checkbox.value
    
    def export(self):
        """Экспорт логов"""
        ui.notify('Log export scheduled', type='info')
    
    def set_max_lines(self, max_lines: int):
        """Установка максимального количества строк"""
        self.max_lines = max_lines


def create_log_viewer(height: str = 'h-96') -> LogViewer:
    """Фабричная функция для создания компонента просмотра логов"""
    viewer = LogViewer()
    viewer.create(height)
    return viewer