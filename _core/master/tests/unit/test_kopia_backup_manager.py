"""Тесты для KopiaBackupManager."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from pathlib import Path
import asyncio
import os
from datetime import datetime, timezone
import json

from app.services.kopia_backup_manager import KopiaBackupManager
from app.models.service import Service
from app.models.backup import Backup
from app.services.backup_models import BackupConfig


@pytest.fixture
def mock_db_session():
    """Мокированная асинхронная сессия БД."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_notifier():
    """Мокированный notifier с методами AppriseNotifier."""
    notifier = AsyncMock()
    notifier.send = AsyncMock()
    notifier.send_backup_completed = AsyncMock()
    notifier.send_backup_failed = AsyncMock()
    notifier.send_retention_pruned = AsyncMock()
    return notifier


@pytest.fixture
def sample_service():
    """Тестовый сервис с конфигурацией бэкапа."""
    service = Service(
        id=1,
        name="test-service",
        display_name="Test Service",
        version="1.0.0",
        description="A test service",
        visibility="public",
        backup_config=BackupConfig(
            enabled=True,
            schedule="0 2 * * *",
            retention_days=7,
            storage_type="kopia",
            kopia_policy={},
        )
    )
    return service


@pytest.fixture
def kopia_backup_manager(mock_db_session, mock_notifier):
    """Экземпляр KopiaBackupManager с моками."""
    manager = KopiaBackupManager(
        db=mock_db_session,
        notifier=mock_notifier,
        dry_run=False,
    )
    # Мокаем пути к скриптам
    manager.scripts_path = Path("/fake/scripts")
    manager.kopia_password = "test-password"
    return manager


class TestKopiaBackupManager:
    """Тесты KopiaBackupManager."""
    
    async def test_run_backup_success(self, kopia_backup_manager, mock_db_session, mock_notifier, sample_service):
        """Успешное выполнение бэкапа."""
        # Настраиваем моки
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_service
        mock_db_session.execute.return_value = mock_result
        
        # Мокаем временную директорию и subprocess
        with patch("tempfile.TemporaryDirectory") as mock_tempdir, \
             patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_tempdir.return_value.__enter__.return_value = "/tmp/test"
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(
                b"Created snapshot with manifest ID: k123456789\nSnapshot size: 1024 bytes",
                b""
            ))
            mock_subprocess.return_value = mock_process
            
            # Мокаем копирование файлов
            with patch.object(kopia_backup_manager, '_copy_service_files', AsyncMock()):
                backup = await kopia_backup_manager.run_backup("test-service")
        
        # Проверяем вызовы
        mock_db_session.execute.assert_called_once()
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()
        mock_notifier.send_backup_completed.assert_called_once_with(
            "test-service", "k123456789", 1024
        )
        assert backup.service_id == 1
        assert backup.status == "completed"
        
    async def test_run_backup_service_not_found(self, kopia_backup_manager, mock_db_session):
        """Ошибка при отсутствии сервиса."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result
        
        with pytest.raises(ValueError, match="Service 'test-service' not found"):
            await kopia_backup_manager.run_backup("test-service")
    
    async def test_run_backup_disabled(self, kopia_backup_manager, mock_db_session, sample_service):
        """Ошибка при отключенном бэкапе."""
        sample_service.backup_config.enabled = False
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_service
        mock_db_session.execute.return_value = mock_result
        
        with pytest.raises(ValueError, match="Backup disabled for service 'test-service'"):
            await kopia_backup_manager.run_backup("test-service")
    
    async def test_run_backup_script_failure(self, kopia_backup_manager, mock_db_session, mock_notifier, sample_service):
        """Ошибка выполнения скрипта бэкапа."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_service
        mock_db_session.execute.return_value = mock_result
        
        with patch("tempfile.TemporaryDirectory") as mock_tempdir, \
             patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_tempdir.return_value.__enter__.return_value = "/tmp/test"
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate = AsyncMock(return_value=(
                b"",
                b"Kopia error: repository not found"
            ))
            mock_subprocess.return_value = mock_process
            
            with patch.object(kopia_backup_manager, '_copy_service_files', AsyncMock()):
                with pytest.raises(RuntimeError, match="Backup script failed"):
                    await kopia_backup_manager.run_backup("test-service")
        
        mock_notifier.send_backup_failed.assert_called_once_with(
            "test-service", "Kopia error: repository not found"
        )
    
    async def test_enforce_retention_success(self, kopia_backup_manager, mock_notifier):
        """Успешное применение политики хранения."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_subprocess.return_value = mock_process
            
            await kopia_backup_manager.enforce_retention("test-service", 7)
        
        # Проверяем вызов скрипта
        mock_subprocess.assert_called_once()
        args = mock_subprocess.call_args[0]
        assert "kopia_policy.sh" in args[1]
        assert "--prune" in args
        assert "--keep-within" in args
        assert "7d" in args
        
        mock_notifier.send_retention_pruned.assert_called_once_with("test-service", 7)
    
    async def test_enforce_retention_failure(self, kopia_backup_manager, mock_notifier):
        """Ошибка применения политики хранения."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate = AsyncMock(return_value=(
                b"",
                b"Policy error"
            ))
            mock_subprocess.return_value = mock_process
            
            with pytest.raises(RuntimeError, match="Retention policy script failed"):
                await kopia_backup_manager.enforce_retention("test-service", 7)
        
        mock_notifier.send.assert_called_once()
        call_args = mock_notifier.send.call_args[0][0]
        assert "Retention policy failed" in call_args
    
    async def test_dry_run_backup(self, kopia_backup_manager, mock_db_session, sample_service):
        """Dry-run бэкапа без реального выполнения."""
        kopia_backup_manager.dry_run = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_service
        mock_db_session.execute.return_value = mock_result
        
        result = await kopia_backup_manager.dry_run_backup("test-service")
        
        assert result["dry_run"] is True
        assert result["service_name"] == "test-service"
        assert result["backup_enabled"] is True
    
    async def test_copy_service_files(self, kopia_backup_manager):
        """Копирование файлов сервиса."""
        service = Service(
            name="test-service",
            visibility="public"
        )
        
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_subprocess.return_value = mock_process
            
            await kopia_backup_manager._copy_service_files(service, Path("/tmp/dest"))
        
        mock_subprocess.assert_called_once()
        args = mock_subprocess.call_args[0]
        assert args[0] == "rsync"
    
    def test_parse_manifest_id(self, kopia_backup_manager):
        """Парсинг manifest_id из вывода скрипта."""
        test_cases = [
            ("Created snapshot with manifest ID: k123456789", "k123456789"),
            ("manifest_id: k987654321", "k987654321"),
            ("Manifest ID: k555555555", "k555555555"),
            ("Snapshot ID: k999999999", "k999999999"),
            ("No ID here", "unknown"),
        ]
        
        for output, expected in test_cases:
            result = kopia_backup_manager._parse_manifest_id(output)
            assert result == expected
    
    def test_parse_snapshot_size(self, kopia_backup_manager):
        """Парсинг размера снапшота."""
        test_cases = [
            ("Snapshot size: 1024 bytes", 1024),
            ("Snapshot size: 0 bytes", 0),
            ("No size info", 0),
        ]
        
        for output, expected in test_cases:
            result = kopia_backup_manager._parse_snapshot_size(output)
            assert result == expected