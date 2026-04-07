"""Компонент индикатора здоровья сервиса."""
from nicegui import ui
from typing import Optional
from datetime import datetime, timezone


class HealthIndicator(ui.column):
    """Компонент индикатора здоровья сервиса.
    
    Пример использования:
        indicator = HealthIndicator()
        indicator.update_status('healthy', response_time=0.25)
    """

    STATUS_CONFIG = {
        'healthy': {'icon': 'check_circle', 'color': 'positive', 'label': 'Здоров'},
        'unhealthy': {'icon': 'error', 'color': 'negative', 'label': 'Нездоров'},
        'warning': {'icon': 'warning', 'color': 'warning', 'label': 'Внимание'},
        'unknown': {'icon': 'help_circle', 'color': 'grey', 'label': 'Неизвестно'},
    }

    def __init__(self, size: str = 'lg', show_label: bool = True):
        """Инициализация индикатора.
        
        Args:
            size: Размер иконки (sm, md, lg, xl)
            show_label: Показывать текстовую метку
        """
        super().__init__()
        
        self._status = 'unknown'
        self._response_time = 0.0
        self._last_checked: Optional[datetime] = None
        self._error: Optional[str] = None
        self._show_label = show_label
        
        self._size_classes = {
            'sm': 'text-sm',
            'md': 'text-2xl',
            'lg': 'text-3xl',
            'xl': 'text-4xl',
        }
        
        with self.classes('items-center gap-1'):
            self._icon = ui.icon('help_circle').classes(self._size_classes.get(size, 'text-2xl'))
            if show_label:
                self._label = ui.label('Неизвестно').classes('text-caption text-grey-7')
                self._time_label = ui.label('').classes('text-xs text-grey-5')
        
        self._update_visual()

    def update_status(self, status: str, response_time: float = 0, 
                      error: Optional[str] = None):
        """Обновление статуса здоровья.
        
        Args:
            status: Статус (healthy, unhealthy, warning, unknown)
            response_time: Время ответа в секундах
            error: Сообщение об ошибке
        """
        self._status = status
        self._response_time = response_time
        self._error = error
        self._last_checked = datetime.now(timezone.utc)
        
        self._update_visual()

    def _update_visual(self):
        """Обновление визуального представления."""
        config = self.STATUS_CONFIG.get(self._status, self.STATUS_CONFIG['unknown'])
        
        # Обновляем иконку
        self._icon.name = config['icon']
        self._icon.classes(replace=f"text-{config['color']}")
        
        # Обновляем метку
        if self._show_label and hasattr(self, '_label'):
            self._label.set_text(config['label'])
            self._label.classes(replace=f"text-{config['color']}")
            
            # Добавляем время ответа если есть
            if self._response_time > 0:
                time_text = f'{self._response_time:.2f}с'
                if hasattr(self, '_time_label'):
                    self._time_label.set_text(time_text)
            elif hasattr(self, '_time_label'):
                self._time_label.set_text('')
        
        # Обновляем подсказку
        tooltip_parts = [f"Статус: {config['label']}"]
        if self._response_time > 0:
            tooltip_parts.append(f"Время ответа: {self._response_time:.2f}с")
        if self._last_checked:
            tooltip_parts.append(f"Проверен: {self._last_checked.strftime('%H:%M:%S')}")
        if self._error:
            tooltip_parts.append(f"Ошибка: {self._error}")
        
        self._icon.tooltip('\n'.join(tooltip_parts))

    def reset(self):
        """Сброс индикатора в состояние unknown."""
        self.update_status('unknown', response_time=0, error=None)


def create_health_indicator(size: str = 'lg', show_label: bool = True) -> HealthIndicator:
    """Фабричная функция для создания индикатора здоровья.
    
    Args:
        size: Размер индикатора
        show_label: Показывать текстовую метку
        
    Returns:
        Экземпляр HealthIndicator
    """
    return HealthIndicator(size=size, show_label=show_label)
