from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from nicegui import ui
import asyncio
import logging

from app.config import settings
from app.core.security import KeycloakAuthProvider, BuiltInAuthProvider, set_auth_provider
from app.core.database import get_async_db, AsyncSessionLocal
from app.core.events import backup_scheduler
from app.services import ServiceDiscovery
from app.services.health_checker import HealthChecker
from app.services.caddy_manager import CaddyManager
from app.services.notifier import TelegramNotifier, AppriseNotifier
from app.services.docker_manager import DockerManager
from app.services.kopia_backup_manager import KopiaBackupManager
from app.services.log_manager import LogManager
from app.api.routes import services, deployments, logs, backups, health, users, tls
from app.ui.theme import apply_theme

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# ГЛОБАЛЬНЫЕ ОБЪЕКТЫ
# ──────────────────────────────────────────────

_background_tasks: list[asyncio.Task] = []


# ──────────────────────────────────────────────
# LIFESPAN УПРАВЛЕНИЕ
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация и очистка ресурсов при старте/остановке приложения."""
    await startup_tasks(app)
    yield
    await shutdown_tasks(app)


async def startup_tasks(app: FastAPI):
    """Задачи при запуске приложения."""
    from app.core.database import db_manager
    db_manager.create_tables()

    # Аутентификация
    auth_provider = (
        BuiltInAuthProvider()
        if settings.AUTH_PROVIDER == "builtin"
        else KeycloakAuthProvider()
    )
    app.state.auth_provider = auth_provider
    set_auth_provider(auth_provider)

    # Инициализация сервисов
    app.state.discovery = ServiceDiscovery(settings.SERVICES_PATH)
    app.state.health_checker = HealthChecker()
    app.state.caddy = CaddyManager(settings.CADDY_CONFIG_PATH)
    
    # Два отдельных notifier: Telegram для общих уведомлений, Apprise для бэкапов
    app.state.telegram_notifier = TelegramNotifier(
        bot_token=settings.TELEGRAM_BOT_TOKEN,
        chat_ids=settings.TELEGRAM_CHAT_IDS
    )
    app.state.apprise_notifier = AppriseNotifier(urls=settings.NOTIFY_URLS)
    
    # Для обратной совместимости оставляем app.state.notifier = TelegramNotifier
    app.state.notifier = app.state.telegram_notifier
    
    app.state.docker = DockerManager(notifier=app.state.telegram_notifier)
    app.state.log_manager = LogManager(
        docker_manager=app.state.docker,
        cache_ttl=settings.LOG_CACHE_TTL,
        cache_size=settings.LOG_CACHE_SIZE,
        safe_export_path=Path(settings.DATA_DIR) / "log_exports"
    )

    # Инициализация KopiaBackupManager (асинхронная сессия) с AppriseNotifier
    from sqlalchemy.ext.asyncio import AsyncSession
    if AsyncSessionLocal:
        async_session = AsyncSessionLocal()
        app.state.backup = KopiaBackupManager(
            db=async_session,
            notifier=app.state.apprise_notifier,  # Используем Apprise для бэкапов
            dry_run=settings.DRY_RUN_BACKUP if hasattr(settings, 'DRY_RUN_BACKUP') else False
        )
        # Для обратной совместимости оставляем app.state.kopia_backup (можно удалить позже)
        app.state.kopia_backup = app.state.backup
    else:
        logger.warning("AsyncSessionLocal not configured, KopiaBackupManager will not be available")
        app.state.backup = None
        app.state.kopia_backup = None
    
    # Проверка legacy таблиц (старый BackupManager)
    if AsyncSessionLocal:
        try:
            from sqlalchemy import inspect, text
            from sqlalchemy.ext.asyncio import AsyncSession
            async with AsyncSessionLocal() as session:
                # Проверяем существование таблиц старого BackupManager
                inspector = inspect(session.get_bind())
                legacy_tables = ['backups', 'backup_schedules', 'restore_jobs']
                existing = [t for t in legacy_tables if inspector.has_table(t)]
                if existing:
                    logger.warning(
                        f"Legacy backup tables detected: {existing}. "
                        "These tables are no longer used by KopiaBackupManager. "
                        "Consider migrating data or dropping tables."
                    )
        except Exception as e:
            logger.debug(f"Could not check legacy tables: {e}")

    # Первоначальная настройка
    await app.state.discovery.scan_all()
    await app.state.caddy.regenerate_all(app.state.discovery.services)

    # Запуск фоновых задач
    background_tasks = [
        health_check_loop(app),
        watch_services_changes(app),
        backup_schedule_loop(app),
    ]
    _background_tasks.extend(asyncio.create_task(task) for task in background_tasks)

    await app.state.telegram_notifier.send("🚀 Platform Master Service started")


async def shutdown_tasks(app: FastAPI):
    """Очистка ресурсов при остановке."""
    await app.state.telegram_notifier.send("🛑 Platform Master Service stopping")

    for task in _background_tasks:
        task.cancel()
    if _background_tasks:
        await asyncio.gather(*_background_tasks, return_exceptions=True)
    _background_tasks.clear()

    await app.state.health_checker.close()


# ──────────────────────────────────────────────
# ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ
# ──────────────────────────────────────────────

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    lifespan=lifespan,
)

# CORS — поддержка '*' через строку
if settings.ALLOWED_ORIGINS == ["*"]:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Публичный маршрут
@app.get("/healthz")
def health_check():
    return {"status": "ok"}


# Подключение маршрутов API
routers = [
    (services.router, "/api/services", ["services"]),
    (deployments.router, "/api/deployments", ["deployments"]),
    (logs.router, "/api/logs", ["logs"]),
    (backups.router, "/api/backups", ["backups"]),
    (health.router, "/api/health", ["health"]),
    (users.router, "/api/users", ["users"]),
    (tls.router, "/api/tls", ["tls"]),
]

for router, prefix, tags in routers:
    app.include_router(router, prefix=prefix, tags=tags)


# ──────────────────────────────────────────────
# ФОНОВЫЕ ЗАДАЧИ
# ──────────────────────────────────────────────

async def health_check_loop(app: FastAPI):
    """Проверка здоровья сервисов каждые 30 секунд."""
    while True:
        try:
            for service in app.state.discovery.services.values():
                status = await app.state.health_checker.check(service)
                if status.changed:
                    msg = (
                        f"🟢 Service {service.name} recovered"
                        if status.is_healthy else
                        f"🔴 Service {service.name} is unhealthy!\n"
                        f"Endpoint: {service.health.endpoint}\nError: {status.error}"
                    )
                    await app.state.telegram_notifier.send(msg)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Health check error: {e}")
        await asyncio.sleep(30)


async def watch_services_changes(app: FastAPI):
    """Отслеживание изменений в конфигурации сервисов."""
    from watchfiles import awatch

    async for changes in awatch(settings.SERVICES_PATH):
        if any("service.yml" in path or "docker-compose.yml" in path for _, path in changes):
            await app.state.discovery.scan_all()
            await app.state.caddy.regenerate_all(app.state.discovery.services)
            await app.state.telegram_notifier.send("🔄 Services configuration updated")


async def backup_schedule_loop(app: FastAPI):
    """Цикл автоматического резервного копирования с использованием KopiaBackupManager."""
    # Если KopiaBackupManager доступен, используем новый планировщик
    if app.state.kopia_backup:
        logger.info("Starting Kopia backup scheduler")
        try:
            await backup_scheduler(app.state.kopia_backup, app.state.discovery)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Kopia backup scheduler error: {e}")
            # Fallback на старый планировщик при ошибке
            logger.warning("Falling back to legacy backup scheduler")
            try:
                await app.state.backup.schedule_loop(app.state.discovery.services)
            except asyncio.CancelledError:
                pass
    else:
        # Если KopiaBackupManager не доступен, используем старый планировщик
        logger.warning("KopiaBackupManager not available, using legacy backup scheduler")
        try:
            await app.state.backup.schedule_loop(app.state.discovery.services)
        except asyncio.CancelledError:
            pass


# ──────────────────────────────────────────────
# NICEGUI UI
# ──────────────────────────────────────────────

# Применяем единую тему
apply_theme()

# Подавляем известный баг NiceGUI с prune_user_storage
logging.getLogger('nicegui.nicegui').addFilter(
    lambda record: 'Request is not set' not in record.getMessage()
)


@ui.page("/")
async def main_page():
    from app.ui.main_page import render_main_page
    await render_main_page()

@ui.page("/services")
async def services_page():
    from app.ui.services_page import render_services_page
    await render_services_page()

@ui.page("/services/{service_name}")
async def service_detail_page(service_name: str):
    ui.navigate.to("/services")

@ui.page("/logs")
async def logs_page():
    from app.ui.logs_page import render_logs_page
    await render_logs_page()

@ui.page("/backups")
async def backups_page():
    from app.ui.backups_page import render_backups_page
    await render_backups_page()

# Запуск UI
ui.run_with(
    app,
    title="Platform Manager",
    favicon="🚀",
    dark=False,  # Светлая тема для более чистого вида
    storage_secret=settings.SECRET_KEY,
)