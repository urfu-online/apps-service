from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from nicegui import ui
import asyncio

from app.config import settings
from app.core.security import KeycloakAuthProvider, BuiltInAuthProvider, set_auth_provider
from app.services import ServiceDiscovery
from app.services.health_checker import HealthChecker
from app.services.caddy_manager import CaddyManager
from app.services.notifier import TelegramNotifier
from app.services.docker_manager import DockerManager
from app.services.backup_manager import BackupManager
from app.services.log_manager import LogManager
from app.api.routes import services, deployments, logs, backups, health, users, tls


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
    app.state.notifier = TelegramNotifier(
        bot_token=settings.TELEGRAM_BOT_TOKEN,
        chat_ids=settings.TELEGRAM_CHAT_IDS
    )
    app.state.docker = DockerManager(notifier=app.state.notifier)
    app.state.backup = BackupManager(notifier=app.state.notifier)
    app.state.log_manager = LogManager()

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

    await app.state.notifier.send("🚀 Platform Master Service started")


async def shutdown_tasks(app: FastAPI):
    """Очистка ресурсов при остановке."""
    await app.state.notifier.send("🛑 Platform Master Service stopping")

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
                    await app.state.notifier.send(msg)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Health check error: {e}")
        await asyncio.sleep(30)


async def watch_services_changes(app: FastAPI):
    """Отслеживание изменений в конфигурации сервисов."""
    from watchfiles import awatch

    async for changes in awatch(settings.SERVICES_PATH):
        if any("service.yml" in path or "docker-compose.yml" in path for _, path in changes):
            await app.state.discovery.scan_all()
            await app.state.caddy.regenerate_all(app.state.discovery.services)
            await app.state.notifier.send("🔄 Services configuration updated")


async def backup_schedule_loop(app: FastAPI):
    """Цикл автоматического резервного копирования."""
    try:
        await app.state.backup.schedule_loop(app.state.discovery.services)
    except asyncio.CancelledError:
        pass


# ──────────────────────────────────────────────
# NICEGUI UI
# ──────────────────────────────────────────────

# Применяем единую тему
from app.ui.theme import apply_theme
apply_theme()

# Подавляем известный баг NiceGUI с prune_user_storage
import logging
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