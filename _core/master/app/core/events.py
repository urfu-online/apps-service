
from typing import Callable, Dict, List, Any, Optional
import asyncio
import logging
from datetime import datetime, timezone
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Event:
    type: str
    data: Any
    timestamp: datetime


class EventBus:
    """
    Шина событий с типизацией, асинхронной подпиской и ограничением истории.
    Поддерживает корутинные и обычные функции-обработчики.
    """

    def __init__(self, max_history: int = 1000):
        self._listeners: Dict[str, List[Callable]] = {}
        self._history: List[Event] = []
        self._max_history = max_history

    def subscribe(self, event_type: str, listener: Callable) -> None:
        """Подписывает обработчик на событие."""
        if not asyncio.iscoroutinefunction(listener) and not callable(listener):
            raise ValueError("Listener must be a callable function or coroutine.")
        self._listeners.setdefault(event_type, []).append(listener)
        logger.debug(f"Подписан на событие '{event_type}'")

    def unsubscribe(self, event_type: str, listener: Callable) -> None:
        """Отписывает обработчик от события."""
        if event_type in self._listeners:
            try:
                self._listeners[event_type].remove(listener)
                logger.debug(f"Отписан от события '{event_type}'")
            except ValueError:
                logger.warning(f"Обработчик не найден при отписке от '{event_type}'")

    async def emit(self, event_type: str, data: Any = None) -> None:
        """Эмитирует событие и вызывает всех подписчиков."""
        event = Event(type=event_type, data=data, timestamp=datetime.now(timezone.utc))
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        tasks = []
        for listener in self._listeners.get(event_type, []):
            if asyncio.iscoroutinefunction(listener):
                tasks.append(listener(data))
            else:
                try:
                    listener(data)
                except Exception as e:
                    logger.error(f"Ошибка в синхронном обработчике '{event_type}': {e}")

        if tasks:
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as e:
                logger.error(f"Ошибка при выполнении асинхронных обработчиков: {e}")

        logger.debug(f"Эмитировано событие '{event_type}'")

    def get_history(self, event_type: Optional[str] = None, limit: int = 100) -> List[Event]:
        """Возвращает историю событий (последние N записей)."""
        filtered = self._history if event_type is None else [e for e in self._history if e.type == event_type]
        return filtered[-limit:]


event_bus = EventBus(max_history=1000)


def on(event_type: str):
    """Декоратор для подписки функции на событие."""
    def decorator(func: Callable):
        event_bus.subscribe(event_type, func)
        return func
    return decorator