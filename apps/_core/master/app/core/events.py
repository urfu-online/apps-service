from typing import Callable, Dict, List, Any
import asyncio
import logging
from datetime import datetime

# Настройка логирования
logger = logging.getLogger(__name__)


class EventBus:
    """Шина событий для обмена сообщениями между компонентами"""
    
    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}
        self._history: List[Dict[str, Any]] = []
        self._max_history = 1000  # Максимальное количество событий в истории
    
    def subscribe(self, event_type: str, listener: Callable):
        """
        Подписка на событие
        
        :param event_type: Тип события
        :param listener: Функция-обработчик события
        """
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        
        self._listeners[event_type].append(listener)
        logger.debug(f"Subscribed to event '{event_type}'")
    
    def unsubscribe(self, event_type: str, listener: Callable):
        """
        Отписка от события
        
        :param event_type: Тип события
        :param listener: Функция-обработчик события
        """
        if event_type in self._listeners:
            try:
                self._listeners[event_type].remove(listener)
                logger.debug(f"Unsubscribed from event '{event_type}'")
            except ValueError:
                pass  # Обработчик не найден в списке
    
    async def emit(self, event_type: str, data: Any = None):
        """
        Эмитация события
        
        :param event_type: Тип события
        :param data: Данные события
        """
        # Сохраняем событие в истории
        event_record = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow()
        }
        
        self._history.append(event_record)
        if len(self._history) > self._max_history:
            self._history.pop(0)  # Удаляем самое старое событие
        
        # Вызываем всех слушателей
        if event_type in self._listeners:
            for listener in self._listeners[event_type]:
                try:
                    if asyncio.iscoroutinefunction(listener):
                        await listener(data)
                    else:
                        listener(data)
                except Exception as e:
                    logger.error(f"Error in event listener for '{event_type}': {e}")
        
        logger.debug(f"Emitted event '{event_type}' with data: {data}")
    
    def get_history(self, event_type: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Получение истории событий
        
        :param event_type: Тип события (опционально)
        :param limit: Максимальное количество событий
        :return: Список событий
        """
        if event_type:
            filtered_history = [e for e in self._history if e["type"] == event_type]
        else:
            filtered_history = self._history
        
        return filtered_history[-limit:]  # Возвращаем последние N событий


# Глобальный экземпляр шины событий
event_bus = EventBus()


# Декоратор для подписки на события
def on(event_type: str):
    """
    Декоратор для подписки на события
    
    :param event_type: Тип события
    """
    def decorator(func: Callable):
        event_bus.subscribe(event_type, func)
        return func
    return decorator