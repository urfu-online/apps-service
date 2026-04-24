"""Тесты для AppriseNotifier."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from app.services.notifier import AppriseNotifier
from app.core.events import event_bus


class TestAppriseNotifier:
    """Тесты AppriseNotifier."""
    
    def test_init_with_apprise_available(self):
        """Инициализация при доступной библиотеке apprise."""
        with patch.dict('sys.modules', {'apprise': MagicMock()}):
            mock_apprise = MagicMock()
            mock_apprise.Apprise.return_value = mock_apprise
            with patch('apprise.Apprise', mock_apprise.Apprise):
                notifier = AppriseNotifier(urls=["telegram://token/chat_id"])
                
                assert notifier._apprise is not None
                mock_apprise.add.assert_called_once_with("telegram://token/chat_id")
    
    def test_init_without_apprise(self):
        """Инициализация без библиотеки apprise."""
        with patch.dict('sys.modules', {'apprise': None}):
            notifier = AppriseNotifier(urls=[])
                
            assert notifier._apprise is None
    
    async def test_send_with_apprise_success(self):
        """Успешная отправка через Apprise."""
        mock_apprise = MagicMock()
        mock_apprise.notify = MagicMock(return_value=True)
        
        with patch.dict('sys.modules', {'apprise': MagicMock()}):
            with patch('apprise.Apprise', return_value=mock_apprise):
                notifier = AppriseNotifier(urls=[])
                
                with patch.object(event_bus, 'emit', AsyncMock()) as mock_emit:
                    with patch('asyncio.get_event_loop') as mock_loop:
                        mock_executor = AsyncMock(return_value=True)
                        mock_loop.return_value.run_in_executor = AsyncMock(return_value=mock_executor)
                        
                        success = await notifier.send("Test message", "Test title")
                        
                        assert success is True
                        mock_emit.assert_called_once_with(
                            "backup.notification",
                            {
                                "title": "Test title",
                                "message": "Test message",
                                "timestamp": pytest.approx(any, rel=1)
                            }
                        )
    
    async def test_send_with_apprise_failure(self):
        """Ошибка отправки через Apprise."""
        mock_apprise = MagicMock()
        mock_apprise.notify = MagicMock(return_value=False)
        
        with patch.dict('sys.modules', {'apprise': MagicMock()}):
            with patch('apprise.Apprise', return_value=mock_apprise):
                notifier = AppriseNotifier(urls=[])
                
                with patch.object(event_bus, 'emit', AsyncMock()):
                    with patch('asyncio.get_event_loop') as mock_loop:
                        mock_executor = AsyncMock(return_value=False)
                        mock_loop.return_value.run_in_executor = AsyncMock(return_value=mock_executor)
                        
                        success = await notifier.send("Test message")
                        
                        assert success is False
    
    async def test_send_without_apprise(self):
        """Отправка без библиотеки apprise (логирование)."""
        with patch.dict('sys.modules', {'apprise': None}):
            notifier = AppriseNotifier(urls=[])
            assert notifier._apprise is None
            
            with patch.object(event_bus, 'emit', AsyncMock()) as mock_emit:
                success = await notifier.send("Test message")
                
                assert success is True
                mock_emit.assert_called_once()
    
    async def test_send_backup_completed(self):
        """Уведомление об успешном бэкапе."""
        mock_apprise = MagicMock()
        mock_apprise.notify = MagicMock(return_value=True)
        
        with patch.dict('sys.modules', {'apprise': MagicMock()}):
            with patch('apprise.Apprise', return_value=mock_apprise):
                notifier = AppriseNotifier(urls=[])
                
                with patch.object(notifier, 'send', AsyncMock()) as mock_send:
                    with patch.object(event_bus, 'emit', AsyncMock()) as mock_emit:
                        await notifier.send_backup_completed("test-service", "k123456789", 1024)
                        
                        mock_send.assert_called_once_with(
                            "✅ Backup completed for test-service\nManifest ID: k123456789\nSize: 1024 bytes",
                            title="Backup Completed"
                        )
                        mock_emit.assert_called_once_with(
                            "backup.completed",
                            {
                                "service_name": "test-service",
                                "manifest_id": "k123456789",
                                "size": 1024,
                                "timestamp": pytest.approx(any, rel=1)
                            }
                        )
    
    async def test_send_backup_failed(self):
        """Уведомление о неудачном бэкапе."""
        mock_apprise = MagicMock()
        mock_apprise.notify = MagicMock(return_value=True)
        
        with patch.dict('sys.modules', {'apprise': MagicMock()}):
            with patch('apprise.Apprise', return_value=mock_apprise):
                notifier = AppriseNotifier(urls=[])
                
                with patch.object(notifier, 'send', AsyncMock()):
                    with patch.object(event_bus, 'emit', AsyncMock()) as mock_emit:
                        await notifier.send_backup_failed("test-service", "Disk full")
                        
                        mock_emit.assert_called_once_with(
                            "backup.failed",
                            {
                                "service_name": "test-service",
                                "error": "Disk full",
                                "timestamp": pytest.approx(any, rel=1)
                            }
                        )
    
    async def test_send_retention_pruned(self):
        """Уведомление о применении политики хранения."""
        mock_apprise = MagicMock()
        mock_apprise.notify = MagicMock(return_value=True)
        
        with patch.dict('sys.modules', {'apprise': MagicMock()}):
            with patch('apprise.Apprise', return_value=mock_apprise):
                notifier = AppriseNotifier(urls=[])
                
                with patch.object(notifier, 'send', AsyncMock()):
                    with patch.object(event_bus, 'emit', AsyncMock()) as mock_emit:
                        await notifier.send_retention_pruned("test-service", 7)
                        
                        mock_emit.assert_called_once_with(
                            "retention.pruned",
                            {
                                "service_name": "test-service",
                                "retention_days": 7,
                                "timestamp": pytest.approx(any, rel=1)
                            }
                        )