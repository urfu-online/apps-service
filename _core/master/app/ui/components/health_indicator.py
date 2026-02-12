from nicegui import ui
from typing import Optional


class HealthIndicator:
    """Компонент индикатора здоровья"""
    
    def __init__(self):
        self.status = 'unknown'
        self.response_time = 0.0
        self.last_checked = ''
        self.error = None
    
    def create(self, size: str = 'text-2xl') -> ui.column:
        """Создание компонента индикатора здоровья"""
        with ui.column().classes('items-center') as column:
            self.status_icon = ui.label('').classes(f'{size}')
            self.status_text = ui.label('').classes('text-caption')
        
        # Устанавливаем начальное состояние
        self.update_status(self.status, self.response_time, self.last_checked, self.error)
        
        return column
    
    def update_status(self, status: str, response_time: float = 0, last_checked: str = '', error: str = None):
        """Обновление статуса индикатора"""
        self.status = status
        self.response_time = response_time
        self.last_checked = last_checked
        self.error = error
        
        # Обновляем отображение
        status_config = {
            'healthy': {'icon': '🟢', 'text': 'Healthy', 'color': 'text-green'},
            'unhealthy': {'icon': '🔴', 'text': 'Unhealthy', 'color': 'text-red'},
            'warning': {'icon': '🟡', 'text': 'Warning', 'color': 'text-yellow'},
            'unknown': {'icon': '⚪', 'text': 'Unknown', 'color': 'text-grey'}
        }
        
        config = status_config.get(status, status_config['unknown'])
        
        # Обновляем иконку
        self.status_icon.set_text(config['icon'])
        self.status_icon.classes(replace=config['color'])
        
        # Обновляем текст
        if response_time > 0:
            self.status_text.set_text(f"{config['text']} ({response_time:.2f}s)")
        else:
            self.status_text.set_text(config['text'])
        
        self.status_text.classes(replace=config['color'])
        
        # Добавляем подсказку с деталями
        tooltip_text = f"Status: {status}\n"
        if last_checked:
            tooltip_text += f"Last checked: {last_checked}\n"
        if response_time > 0:
            tooltip_text += f"Response time: {response_time:.2f}s\n"
        if error:
            tooltip_text += f"Error: {error}"
        
        self.status_icon.tooltip(tooltip_text)


def create_health_indicator(size: str = 'text-2xl') -> HealthIndicator:
    """Фабричная функция для создания компонента индикатора здоровья"""
    indicator = HealthIndicator()
    indicator.create(size)
    return indicator