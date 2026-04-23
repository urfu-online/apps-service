from typing import Optional, List
import html
import aiohttp
from datetime import datetime, timezone
import logging

from app.config import settings
from app.core.events import event_bus

# Настройка логирования
logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Уведомления в Telegram"""
    
    def __init__(
        self, 
        bot_token: str, 
        chat_ids: Optional[List[str]] = None
    ):
        self.bot_token = bot_token
        self.chat_ids = chat_ids or []
        self.api_base = f"https://api.telegram.org/bot{bot_token}"
    
    async def send(
        self, 
        message: str, 
        chat_id: Optional[str] = None,
        parse_mode: str = "HTML"
    ) -> bool:
        """Отправка сообщения"""
        targets = [chat_id] if chat_id else self.chat_ids
        
        if not targets:
            logger.warning("No chat IDs configured for Telegram notifications")
            return False
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        full_message = f"<b>🖥 Platform Alert</b>\n<i>{timestamp}</i>\n\n{message}"
        
        success = True
        async with aiohttp.ClientSession() as session:
            for target in targets:
                try:
                    async with session.post(
                        f"{self.api_base}/sendMessage",
                        json={
                            "chat_id": target,
                            "text": full_message,
                            "parse_mode": parse_mode,
                            "disable_web_page_preview": True
                        }
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            logger.error(f"Telegram send failed for chat {target}: {error_text}")
                            success = False
                        else:
                            logger.info(f"Message sent to Telegram chat {target}")
                except Exception as e:
                    logger.error(f"Telegram send error to chat {target}: {e}")
                    success = False
        
        return success
    
    async def send_service_status(
        self, 
        service_name: str,
        status: str,
        details: Optional[str] = None
    ):
        """Уведомление о статусе сервиса"""
        emoji_map = {
            "running": "🟢",
            "stopped": "🔴",
            "error": "❌",
            "warning": "🟡",
            "deploying": "🔄"
        }
        
        emoji = emoji_map.get(status, "⚪")
        message = f"{emoji} <b>{service_name}</b>: {status}"
        
        if details:
            message += f"\n<pre>{html.escape(details)}</pre>"

        await self.send(message)

    async def send_deployment_notification(
        self,
        service_name: str,
        version: str,
        status: str,
        details: Optional[str] = None
    ):
        """Уведомление о деплое"""
        status_emoji = {
            "success": "✅",
            "failed": "❌",
            "in_progress": "🔄"
        }.get(status, "⚪")
        
        message = f"{status_emoji} <b>Deployment</b>: {service_name} v{version}"
        
        if details:
            message += f"\n<pre>{html.escape(details)}</pre>"

        await self.send(message)

    async def send_backup_notification(
        self,
        service_name: str,
        backup_name: str,
        status: str,
        details: Optional[str] = None
    ):
        """Уведомление о бэкапе"""
        status_emoji = {
            "completed": "✅",
            "failed": "❌",
            "in_progress": "🔄"
        }.get(status, "⚪")
        
        message = f"{status_emoji} <b>Backup</b>: {service_name} ({backup_name})"
        
        if details:
            message += f"\n<pre>{html.escape(details)}</pre>"

        await self.send(message)


class AppriseNotifier:
    """Уведомления через Apprise (поддерживает множество сервисов)."""

    def __init__(self, urls: List[str] = None):
        self.urls = urls or []
        self._apprise = None
        self._init_apprise()

    def _init_apprise(self):
        """Инициализирует Apprise, если библиотека доступна."""
        try:
            import apprise
            self._apprise = apprise.Apprise()
            for url in self.urls:
                self._apprise.add(url)
            logger.info(f"Apprise notifier initialized with {len(self.urls)} URLs")
        except ImportError:
            logger.warning("Apprise library not installed, notifications will be logged only")
            self._apprise = None

    async def send(self, message: str, title: str = "Platform Backup") -> bool:
        """
        Отправляет уведомление через Apprise.

        Args:
            message: текст уведомления
            title: заголовок уведомления

        Returns:
            True если отправка успешна или Apprise не установлен (логируется)
        """
        # Эмитируем событие backup.notification
        await event_bus.emit("backup.notification", {
            "title": title,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        if self._apprise is None:
            logger.info(f"Apprise not available, would send: {title}: {message}")
            return True

        # Apprise поддерживает синхронную отправку, обернём в thread
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            # Apprise не имеет асинхронного API, используем run_in_executor
            success = await loop.run_in_executor(
                None, self._apprise.notify, message, title
            )
            if success:
                logger.info(f"Apprise notification sent: {title}")
            else:
                logger.error(f"Apprise notification failed: {title}")
            return success
        except Exception as e:
            logger.error(f"Apprise notification error: {e}")
            return False

    async def send_backup_completed(self, service_name: str, manifest_id: str, size: int):
        """Уведомление об успешном бэкапе."""
        message = (
            f"✅ Backup completed for {service_name}\n"
            f"Manifest ID: {manifest_id}\n"
            f"Size: {size} bytes"
        )
        await self.send(message, title="Backup Completed")
        await event_bus.emit("backup.completed", {
            "service_name": service_name,
            "manifest_id": manifest_id,
            "size": size,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def send_backup_failed(self, service_name: str, error: str):
        """Уведомление о неудачном бэкапе."""
        message = f"❌ Backup failed for {service_name}\nError: {error}"
        await self.send(message, title="Backup Failed")
        await event_bus.emit("backup.failed", {
            "service_name": service_name,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def send_retention_pruned(self, service_name: str, retention_days: int):
        """Уведомление о применении политики хранения."""
        message = f"🧹 Retention policy applied for {service_name}\nKeep within: {retention_days} days"
        await self.send(message, title="Retention Policy Applied")
        await event_bus.emit("retention.pruned", {
            "service_name": service_name,
            "retention_days": retention_days,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })