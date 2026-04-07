from typing import Optional, List
import html
import aiohttp
from datetime import datetime, timezone
import logging

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