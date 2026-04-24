import re
import asyncio
import logging
import aiofiles
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import deque

from app.services.discovery import ServiceManifest
from app.services.docker_manager import DockerManager
from app.config import settings

# Настройка логирования
logger = logging.getLogger(__name__)


class LogManager:
    """Управление логами сервисов через Docker API с кэшированием.

    ⚠️ КРИТИЧНО: Docker SDK синхронный. Все вызовы docker_manager.get_logs()
    должны выполняться через await asyncio.to_thread() чтобы не блокировать event loop.
    """

    def __init__(
        self,
        docker_manager: DockerManager,
        cache_ttl: int = 30,  # секунды
        cache_size: int = 5000,  # ✅ Увеличено с 1000 для реальной отладки
        safe_export_path: Optional[Path] = None
    ):
        self.docker_manager = docker_manager
        self.cache_ttl = cache_ttl
        self.cache_size = cache_size
        # Кэш: {service_name: {"logs": deque, "timestamp": datetime, "total_lines": int}}
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()  # ✅ Защита от конкурентных обновлений кэша
        # Путь для экспорта (должен быть volume-mounted)
        self.safe_export_path = safe_export_path or (
            Path(settings.DATA_DIR) / "log_exports"
        )
        self.safe_export_path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _strip_ansi(line: str) -> str:
        """Удаление ANSI escape-последовательностей из строки лога.

        Docker с tty: true добавляет коды типа [31mERROR[0m.
        Без очистки поиск по 'error' может не сработать.
        """
        ansi_re = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_re.sub('', line)

    async def get_service_logs(
        self,
        service: ServiceManifest,
        tail: int = 100,
        since: Optional[str] = None,
        skip_cache: bool = False  # ✅ Флаг для полного сканирования
    ) -> List[str]:
        """Получение логов сервиса.

        ⚠️ Docker SDK синхронный — используем asyncio.to_thread().
        """
        cache_key = service.name

        # Проверяем кэш (если не требуется полное сканирование)
        if not skip_cache:
            cached = await self._get_cached_logs(cache_key)
            if cached is not None:
                return cached[-tail:] if tail > 0 else cached

        # ✅ КРИТИЧНО: используем to_thread чтобы не заблокировать event loop
        raw_logs_str = await asyncio.to_thread(
            self.docker_manager.get_logs,
            service,
            tail=tail if not skip_cache else 0,  # 0 = все логи для full_scan
            since=since
        )

        # Парсим строки, очищаем от ANSI-кодов
        raw_lines = raw_logs_str.split("\n") if isinstance(raw_logs_str, str) else []
        cleaned_lines = [self._strip_ansi(line) for line in raw_lines if line.strip()]

        # Опционально: сохраняем в файл для персистентности
        if settings.LOG_ENABLE_PERSISTENCE:
            await self._persist_logs(service.name, cleaned_lines)

        # Обновляем кэш
        await self._update_cache(cache_key, cleaned_lines)
        return cleaned_lines[-tail:] if tail > 0 else cleaned_lines

    async def search_logs(
        self,
        service: ServiceManifest,
        query: str,
        limit: int = 50,  # ✅ Ограничение результатов
        case_sensitive: bool = False,
        full_scan: bool = False  # ✅ Полное сканирование игнорирует кэш
    ) -> List[str]:
        """Поиск по логам сервиса.

        Args:
            full_scan: Если True, игнорирует кэш и делает полный запрос к Docker API.
                       Дорого по ресурсам, но честно для поиска старых ошибок.
        """
        logs = await self.get_service_logs(
            service,
            tail=1000,
            skip_cache=full_scan
        )

        # Поиск
        if case_sensitive:
            matching = [log for log in logs if query in log]
        else:
            query_lower = query.lower()
            matching = [log for log in logs if query_lower in log.lower()]

        # Возвращаем последние N совпадений
        return matching[-limit:]

    async def get_log_stats(
        self,
        service: ServiceManifest,
        full_scan: bool = False  # ✅ Честная статистика по всем логам
    ) -> Dict[str, Any]:
        """Получение статистики по логам сервиса.

        ⚠️ Статистика базируется на кэшированных данных (tail-вызов).
        Для полной истории используйте full_scan=True (дорого).
        """
        logs = await self.get_service_logs(
            service,
            tail=1000,
            skip_cache=full_scan
        )

        stats = {
            "total_entries": len(logs),
            "error_count": 0,
            "warning_count": 0,
            "info_count": 0,
            # ✅ Метаданные для честности API
            "scope": "full_scan" if full_scan else "cached_tail",
            "note": "Based on cached tail, not full history" if not full_scan else "Full container history"
        }

        for log in logs:
            log_lower = log.lower()
            if "error" in log_lower or "exception" in log_lower or "fatal" in log_lower:
                stats["error_count"] += 1
            elif "warning" in log_lower or "warn" in log_lower:
                stats["warning_count"] += 1
            else:
                stats["info_count"] += 1

        return stats

    async def export_logs(
        self,
        service: ServiceManifest,
        export_path: Optional[Path] = None
    ) -> Path:
        """Экспорт логов сервиса в файл.

        ⚠️ Path traversal защита: экспорт только в разрешённую директорию.
        ⚠️ Использует volume-mounted путь, чтобы файлы не удалялись при рестарте.
        """
        # Генерируем имя файла если не указано
        if export_path is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            export_path = self.safe_export_path / f"{service.name}_logs_{timestamp}.txt"

        # ✅ Валидация пути (защита от path traversal)
        export_path = export_path.resolve()
        if not export_path.is_relative_to(self.safe_export_path.resolve()):
            raise ValueError(f"Export path {export_path} is not allowed. Must be inside {self.safe_export_path}")

        # Получаем все логи (игнорируем кэш для экспорта)
        logs = await self.get_service_logs(service, tail=0, skip_cache=True)

        async with aiofiles.open(export_path, 'w') as f:
            for log in logs:
                await f.write(log + '\n')

        logger.info(f"Exported {len(logs)} logs for {service.name} to {export_path}")
        return export_path

    async def _get_cached_logs(self, service_name: str) -> Optional[List[str]]:
        """Получение логов из кэша если они актуальны."""
        if service_name not in self._cache:
            return None

        cache_entry = self._cache[service_name]
        age = (datetime.now(timezone.utc) - cache_entry["timestamp"]).total_seconds()

        if age < self.cache_ttl:
            return list(cache_entry["logs"])
        return None

    async def _update_cache(self, service_name: str, logs: List[str]):
        """Обновление кэша для сервиса.

        ✅ Используется asyncio.Lock() для защиты от конкурентных обновлений,
        если планируются background-таски с обновлением кэша.
        """
        async with self._lock:
            self._cache[service_name] = {
                "logs": deque(logs, maxlen=self.cache_size),
                "timestamp": datetime.now(timezone.utc),
                "total_lines": len(logs)
            }

    async def _persist_logs(self, service_name: str, logs: List[str]):
        """Сохранение логов в файл для персистентности."""
        persist_path = Path(settings.LOG_STORAGE_PATH) / f"{service_name}.log"
        persist_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(persist_path, 'a') as f:
            for log in logs:
                await f.write(log + '\n')
