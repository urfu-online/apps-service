import asyncio
import aiohttp
from typing import Dict, Optional
import logging
from datetime import datetime

from app.services.discovery import ServiceManifest

# Настройка логирования
logger = logging.getLogger(__name__)


class HealthStatus:
    """Статус здоровья сервиса"""
    
    def __init__(self, is_healthy: bool, response_time: float = 0, error: str = None):
        self.is_healthy = is_healthy
        self.response_time = response_time
        self.error = error
        self.checked_at = datetime.utcnow()
        self.changed = False  # Флаг изменения статуса
    
    def __repr__(self):
        return f"<HealthStatus is_healthy={self.is_healthy} response_time={self.response_time}>"


class HealthChecker:
    """Проверка здоровья сервисов"""
    
    def __init__(self):
        self.session = aiohttp.ClientSession()
        self.previous_status: Dict[str, bool] = {}  # Предыдущий статус сервисов
    
    async def check(self, service: ServiceManifest) -> HealthStatus:
        """Проверка здоровья сервиса"""
        if not service.health.enabled:
            return HealthStatus(is_healthy=True, error="Health check disabled")
        
        # Определяем URL для проверки
        url = await self._get_health_url(service)
        if not url:
            return HealthStatus(is_healthy=False, error="Could not determine health check URL")
        
        # Выполняем проверку
        start_time = datetime.utcnow()
        try:
            async with self.session.get(
                url, 
                timeout=aiohttp.ClientTimeout(total=service.health.timeout)
            ) as response:
                response_time = (datetime.utcnow() - start_time).total_seconds()
                
                if response.status == 200:
                    status = HealthStatus(is_healthy=True, response_time=response_time)
                else:
                    status = HealthStatus(
                        is_healthy=False, 
                        response_time=response_time,
                        error=f"HTTP {response.status}"
                    )
        except asyncio.TimeoutError:
            response_time = (datetime.utcnow() - start_time).total_seconds()
            status = HealthStatus(
                is_healthy=False,
                response_time=response_time,
                error="Timeout"
            )
        except Exception as e:
            response_time = (datetime.utcnow() - start_time).total_seconds()
            status = HealthStatus(
                is_healthy=False,
                response_time=response_time,
                error=str(e)
            )
        
        # Проверяем изменение статуса
        previous_healthy = self.previous_status.get(service.name, True)
        status.changed = (previous_healthy != status.is_healthy)
        self.previous_status[service.name] = status.is_healthy
        
        return status
    
    async def _get_health_url(self, service: ServiceManifest) -> Optional[str]:
        """Получение URL для проверки здоровья"""
        # В упрощенной реализации возвращаем базовый URL + endpoint
        # В реальной реализации нужно определить правильный URL на основе маршрутизации
        
        # Проверяем маршруты сервиса
        for route in service.routing:
            if route.type == "domain" and route.domain:
                return f"https://{route.domain}{service.health.endpoint}"
            elif route.type == "subfolder" and route.base_domain and route.path:
                return f"https://{route.base_domain}{route.path}{service.health.endpoint}"
            elif route.type == "port" and route.port:
                return f"http://localhost:{route.port}{service.health.endpoint}"
        
        # Если не нашли подходящий маршрут, возвращаем None
        return None
    
    async def close(self):
        """Закрытие сессии"""
        await self.session.close()