import asyncio
from pathlib import Path
from typing import Dict, List, Optional
import logging
from datetime import datetime, timezone
import aiofiles
from collections import deque

from app.services.discovery import ServiceManifest
from app.config import settings

# Настройка логирования
logger = logging.getLogger(__name__)


class LogManager:
    """Управление логами сервисов"""
    
    def __init__(self, log_base_path: str = None):
        self.log_base_path = Path(log_base_path or settings.SERVICES_PATH)
        self.log_cache: Dict[str, deque] = {}  # Кэш последних логов
        self.cache_size = 1000  # Максимальное количество записей в кэше
    
    async def get_service_logs(
        self, 
        service: ServiceManifest, 
        tail: int = 100,
        since: Optional[str] = None
    ) -> List[str]:
        """
        Получение логов сервиса
        
        :param service: Манифест сервиса
        :param tail: Количество последних строк
        :param since: Время начала (ISO формат)
        :return: Список строк логов
        """
        # В упрощенной реализации возвращаем логи из кэша
        # В реальной реализации здесь будет взаимодействие с Loki или Docker API
        
        cache_key = service.name
        if cache_key not in self.log_cache:
            self.log_cache[cache_key] = deque(maxlen=self.cache_size)
        
        # Возвращаем последние N записей из кэша
        logs = list(self.log_cache[cache_key])
        if tail > 0:
            logs = logs[-tail:]
        
        return logs
    
    async def add_log_entry(self, service_name: str, log_entry: str):
        """
        Добавление записи в логи сервиса
        
        :param service_name: Имя сервиса
        :param log_entry: Запись лога
        """
        if service_name not in self.log_cache:
            self.log_cache[service_name] = deque(maxlen=self.cache_size)
        
        # Добавляем временную метку если её нет
        if not log_entry.startswith('['):
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"[{timestamp}] {log_entry}"
        
        self.log_cache[service_name].append(log_entry)
    
    async def search_logs(
        self, 
        service: ServiceManifest,
        query: str,
        limit: int = 100
    ) -> List[str]:
        """
        Поиск по логам сервиса
        
        :param service: Манифест сервиса
        :param query: Поисковый запрос
        :param limit: Максимальное количество результатов
        :return: Список строк логов, соответствующих запросу
        """
        logs = await self.get_service_logs(service, tail=1000)  # Получаем последние 1000 записей
        matching_logs = [log for log in logs if query.lower() in log.lower()]
        return matching_logs[-limit:]  # Возвращаем последние N совпадений
    
    async def get_log_stats(self, service: ServiceManifest) -> Dict[str, int]:
        """
        Получение статистики по логам сервиса
        
        :param service: Манифест сервиса
        :return: Словарь со статистикой
        """
        logs = await self.get_service_logs(service, tail=1000)
        
        stats = {
            "total_entries": len(logs),
            "error_count": 0,
            "warning_count": 0,
            "info_count": 0
        }
        
        for log in logs:
            if "error" in log.lower() or "exception" in log.lower():
                stats["error_count"] += 1
            elif "warning" in log.lower() or "warn" in log.lower():
                stats["warning_count"] += 1
            else:
                stats["info_count"] += 1
        
        return stats
    
    async def export_logs(
        self, 
        service: ServiceManifest, 
        export_path: Path
    ) -> bool:
        """
        Экспорт логов сервиса в файл
        
        :param service: Манифест сервиса
        :param export_path: Путь для экспорта
        :return: Успешность операции
        """
        try:
            logs = await self.get_service_logs(service, tail=0)  # Все логи
            
            export_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(export_path, 'w') as f:
                for log in logs:
                    await f.write(log + '\n')
            
            logger.info(f"Exported logs for {service.name} to {export_path}")
            return True
        except Exception as e:
            logger.error(f"Error exporting logs for {service.name}: {e}")
            return False