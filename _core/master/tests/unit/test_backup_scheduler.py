"""Тесты для планировщика резервного копирования."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
from datetime import datetime, timezone

from app.core.events import backup_scheduler, get_due_backup_services
from app.services.kopia_backup_manager import KopiaBackupManager
from app.services.discovery import ServiceDiscovery
from app.models.service import Service
from app.services.backup_models import BackupConfig


class TestBackupScheduler:
    """Тесты планировщика резервного копирования."""
    
    @pytest.fixture
    def mock_kopia_manager(self):
        """Мокированный KopiaBackupManager."""
        manager = AsyncMock(spec=KopiaBackupManager)
        manager.run_backup = AsyncMock()
        manager.enforce_retention = AsyncMock()
        return manager
    
    @pytest.fixture
    def mock_discovery(self):
        """Мокированный ServiceDiscovery."""
        discovery = AsyncMock(spec=ServiceDiscovery)
        discovery.services = {}
        return discovery
    
    async def test_backup_scheduler_normal_operation(self, mock_kopia_manager, mock_discovery):
        """Нормальная работа планировщика."""
        # Настраиваем моки
        mock_discovery.services = {
            "service1": Service(
                name="service1",
                backup_config=BackupConfig(
                    enabled=True,
                    schedule="* * * * *",  # каждую минуту
                    retention_days=7,
                    storage_type="kopia",
                )
            )
        }
        
        with patch('app.core.events.get_due_backup_services', AsyncMock()) as mock_get_due:
            mock_get_due.return_value = [("service1", mock_discovery.services["service1"])]
            
            with patch('asyncio.sleep', AsyncMock()) as mock_sleep:
                # Запускаем планировщик на одну итерацию
                task = asyncio.create_task(backup_scheduler(mock_kopia_manager, mock_discovery))
                await asyncio.sleep(0.1)  # Даём время выполниться
                task.cancel()
                
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                
                # Проверяем вызовы
                mock_get_due.assert_called_once_with(mock_discovery)
                mock_kopia_manager.run_backup.assert_called_once_with("service1")
                mock_kopia_manager.enforce_retention.assert_called_once_with("service1", 7)
                mock_sleep.assert_called_once_with(60)
    
    async def test_backup_scheduler_no_due_services(self, mock_kopia_manager, mock_discovery):
        """Планировщик не выполняет бэкап, если нет сервисов для бэкапа."""
        with patch('app.core.events.get_due_backup_services', AsyncMock()) as mock_get_due:
            mock_get_due.return_value = []
            
            with patch('asyncio.sleep', AsyncMock()) as mock_sleep:
                task = asyncio.create_task(backup_scheduler(mock_kopia_manager, mock_discovery))
                await asyncio.sleep(0.1)
                task.cancel()
                
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                
                mock_get_due.assert_called_once_with(mock_discovery)
                mock_kopia_manager.run_backup.assert_not_called()
                mock_sleep.assert_called_once_with(60)
    
    async def test_backup_scheduler_error_handling(self, mock_kopia_manager, mock_discovery):
        """Обработка ошибок в планировщике с увеличением задержки."""
        with patch('app.core.events.get_due_backup_services', AsyncMock()) as mock_get_due:
            mock_get_due.side_effect = Exception("Test error")
            
            with patch('asyncio.sleep', AsyncMock()) as mock_sleep:
                task = asyncio.create_task(backup_scheduler(mock_kopia_manager, mock_discovery))
                await asyncio.sleep(0.1)
                task.cancel()
                
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                
                # При ошибке sleep должен быть вызван с увеличенной задержкой
                mock_sleep.assert_called_once_with(60)  # Первая ошибка: 60 секунд
    
    async def test_get_due_backup_services(self):
        """Определение сервисов, для которых наступило время бэкапа."""
        # Создаём мок discovery с сервисами
        mock_discovery = AsyncMock(spec=ServiceDiscovery)
        
        # Сервис с включённым бэкапом и cron-расписанием, которое срабатывает сейчас
        service1 = Service(
            name="service1",
            backup_config=BackupConfig(
                enabled=True,
                schedule="* * * * *",  # каждую минуту
                retention_days=7,
                storage_type="kopia",
            )
        )
        
        # Сервис с отключённым бэкапом
        service2 = Service(
            name="service2",
            backup_config=BackupConfig(
                enabled=False,
                schedule="* * * * *",
                retention_days=7,
                storage_type="kopia",
            )
        )
        
        # Сервис без конфигурации бэкапа
        service3 = Service(
            name="service3",
            backup_config=None
        )
        
        mock_discovery.services = {
            "service1": service1,
            "service2": service2,
            "service3": service3,
        }
        
        with patch('croniter.croniter') as mock_croniter:
            mock_iter = MagicMock()
            mock_iter.get_next.return_value = datetime.now(timezone.utc).timestamp() - 10  # Время прошло
            mock_croniter.return_value = mock_iter
            
            due_services = await get_due_backup_services(mock_discovery)
            
            # Должен вернуться только service1
            assert len(due_services) == 1
            assert due_services[0][0] == "service1"
            assert due_services[0][1] == service1
    
    async def test_get_due_backup_services_not_due(self):
        """Сервисы, для которых время бэкапа ещё не наступило."""
        mock_discovery = AsyncMock(spec=ServiceDiscovery)
        
        service = Service(
            name="service1",
            backup_config=BackupConfig(
                enabled=True,
                schedule="0 0 * * *",  # раз в день в полночь
                retention_days=7,
                storage_type="kopia",
            )
        )
        
        mock_discovery.services = {"service1": service}
        
        with patch('croniter.croniter') as mock_croniter:
            mock_iter = MagicMock()
            mock_iter.get_next.return_value = datetime.now(timezone.utc).timestamp() + 3600  # Через час
            mock_croniter.return_value = mock_iter
            
            due_services = await get_due_backup_services(mock_discovery)
            
            assert len(due_services) == 0
    
    async def test_get_due_backup_services_invalid_cron(self):
        """Сервис с некорректным cron-выражением пропускается."""
        mock_discovery = AsyncMock(spec=ServiceDiscovery)
        
        service = Service(
            name="service1",
            backup_config=BackupConfig(
                enabled=True,
                schedule="invalid-cron",
                retention_days=7,
                storage_type="kopia",
            )
        )
        
        mock_discovery.services = {"service1": service}
        
        with patch('croniter.croniter', side_effect=ValueError("Invalid cron")):
            due_services = await get_due_backup_services(mock_discovery)
            
            assert len(due_services) == 0