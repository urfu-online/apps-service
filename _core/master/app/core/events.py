
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


# ──────────────────────────────────────────────
# ПЛАНИРОВЩИК РЕЗЕРВНОГО КОПИРОВАНИЯ KOPIA
# ──────────────────────────────────────────────

import asyncio
import logging
from datetime import datetime, timezone
from croniter import croniter
from typing import Optional

from app.services.kopia_backup_manager import KopiaBackupManager
from app.services.discovery import ServiceDiscovery
from app.config import settings

logger = logging.getLogger(__name__)


async def backup_scheduler(manager: KopiaBackupManager, discovery: ServiceDiscovery):
    """
    Планировщик резервного копирования на основе Kopia.

    Цикл с asyncio.sleep(60) и проверкой get_due_backup_services() (croniter).
    Обработка исключений и backoff при ошибках (sleep 300 секунд).

    Args:
        manager: экземпляр KopiaBackupManager
        discovery: экземпляр ServiceDiscovery для получения списка сервисов
    """
    error_backoff = 0  # секунды задержки при ошибках
    while True:
        try:
            if error_backoff > 0:
                logger.warning(f"Backoff after error: sleeping {error_backoff} seconds")
                await asyncio.sleep(error_backoff)
                error_backoff = 0

            # Получаем сервисы, для которых пора выполнить бэкап
            due_services = await get_due_backup_services(discovery)
            for service_name, service in due_services:
                logger.info(f"Starting scheduled backup for service '{service_name}'")
                try:
                    await manager.run_backup(service_name)
                    # Применяем политику хранения
                    retention_days = service.backup_config.retention_days if service.backup_config else 7
                    await manager.enforce_retention(service_name, retention_days)
                except Exception as e:
                    logger.error(f"Failed to backup service '{service_name}': {e}")
                    # Отправляем уведомление об ошибке через менеджер
                    await manager.notifier.send(
                        f"❌ Scheduled backup failed for {service_name}\n"
                        f"Error: {e}"
                    )
                    # Увеличиваем backoff для следующей итерации
                    error_backoff = min(error_backoff + 60, 300)  # максимум 5 минут

            # Ожидание следующей проверки
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info("Backup scheduler cancelled")
            break
        except Exception as e:
            logger.error(f"Unexpected error in backup scheduler: {e}")
            error_backoff = min(error_backoff + 60, 300)
            await asyncio.sleep(error_backoff)


async def get_due_backup_services(discovery: ServiceDiscovery) -> list[tuple[str, Any]]:
    """
    Возвращает список сервисов, для которых наступило время бэкапа согласно расписанию.

    Использует croniter для проверки cron-выражения из backup_config.schedule.
    Сохраняет время последнего запуска в памяти (в production следует использовать БД).

    Returns:
        Список кортежей (service_name, service)
    """
    from app.models.service import Service
    now = datetime.now(timezone.utc)
    due_services = []

    # Простой in-memory кэш последних запусков
    if not hasattr(get_due_backup_services, "_last_run"):
        get_due_backup_services._last_run = {}

    for service_name, service in discovery.services.items():
        if not service.backup_config or not service.backup_config.enabled:
            continue

        schedule = service.backup_config.schedule
        last_run = get_due_backup_services._last_run.get(service_name)

        try:
            cron = croniter(schedule, now)
            next_run = cron.get_next(datetime)
            # Если последний запуск был после next_run? Нужно сравнивать.
            # Упрощённо: если next_run находится в прошлом (или в пределах окна 60 секунд)
            # и последний запуск был раньше next_run, то пора.
            window = 60  # секунд
            if (now - next_run).total_seconds() <= window and (last_run is None or last_run < next_run):
                due_services.append((service_name, service))
                get_due_backup_services._last_run[service_name] = now
        except Exception as e:
            logger.error(f"Invalid cron schedule for service '{service_name}': {schedule}, error: {e}")

    return due_services