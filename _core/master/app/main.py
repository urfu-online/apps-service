import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from nicegui import ui

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

# Таймаут graceful shutdown: 10 секунд на остановку всех воркеров,
# после чего незавершённые задачи форс-канселятся.
SHUTDOWN_TIMEOUT_SECONDS = 10.0


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
    logger.info(
        f"SECRET_KEY loaded, length={len(settings.SECRET_KEY)}, "
        f"source={'env' if os.getenv('SECRET_KEY') else 'default'}, env={settings.ENV}"
    )
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
    """Корректная остановка приложения.

    Шаги (каждый обёрнут в try/except, чтобы один сбойный ресурс не блокировал
    остальные):
      1. Уведомление в Telegram.
      2. Отмена и ожидание фоновых задач с таймаутом ``SHUTDOWN_TIMEOUT_SECONDS``.
      3. Остановка watchdog-обозревателя discovery.
      4. Закрытие health-checker.
      5. Закрытие async backup session (если есть).
      6. Закрытие Docker-клиента (если есть метод).
      7. Очистка кэша логов.
    """
    started_at = time.monotonic()

    try:
        await app.state.telegram_notifier.send("🛑 Platform Master Service stopping")
    except Exception as exc:  # noqa: BLE001 — best-effort, не блокируем shutdown
        logger.warning("Telegram notify on shutdown failed: %s", exc)

    # 2. Фоновые задачи — отменяем и ждём с таймаутом
    for task in _background_tasks:
        if not task.done():
            task.cancel()
    if _background_tasks:
        try:
            await asyncio.wait_for(
                asyncio.gather(*_background_tasks, return_exceptions=True),
                timeout=SHUTDOWN_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Background tasks did not finish within %.1fs; force-cancelling",
                SHUTDOWN_TIMEOUT_SECONDS,
            )
            for task in _background_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*_background_tasks, return_exceptions=True)
    _background_tasks.clear()

    # 3. Watcher — вызываем отдельной попыткой (внутри свой try/except)
    async def _safe(coro_fn, name: str) -> None:
        try:
            await coro_fn()
        except Exception as exc:  # noqa: BLE001
            logger.warning("shutdown step %s failed: %s", name, exc)

    if hasattr(app.state, "discovery") and app.state.discovery is not None:
        # stop_watcher в discovery — синхронный, обернём в to_thread
        try:
            await asyncio.to_thread(app.state.discovery.stop_watcher)
        except Exception as exc:  # noqa: BLE001
            logger.warning("discovery.stop_watcher failed: %s", exc)

    # 4. HealthChecker
    if hasattr(app.state, "health_checker") and app.state.health_checker is not None:
        await _safe(app.state.health_checker.close(), "health_checker.close")

    # 5. KopiaBackupManager — закрываем async-сессию, если она была создана
    backup = getattr(app.state, "backup", None) or getattr(app.state, "kopia_backup", None)
    if backup is not None:
        session = getattr(backup, "db", None)
        if session is not None:
            try:
                await session.close()
            except Exception as exc:  # noqa: BLE001
                logger.warning("backup session close failed: %s", exc)

    # 6. Docker manager — закрываем, если есть соответствующий метод
    if hasattr(app.state, "docker") and app.state.docker is not None:
        close = getattr(app.state.docker, "close", None)
        if callable(close):
            try:
                result = close()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:  # noqa: BLE001
                logger.warning("docker.close failed: %s", exc)

    # 7. LogManager — сбрасываем кэш, если есть метод
    if hasattr(app.state, "log_manager") and app.state.log_manager is not None:
        flush = getattr(app.state.log_manager, "flush", None) or getattr(
            app.state.log_manager, "close", None
        )
        if callable(flush):
            try:
                result = flush()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:  # noqa: BLE001
                logger.warning("log_manager.flush/close failed: %s", exc)

    duration_ms = int((time.monotonic() - started_at) * 1000)
    logger.info(
        "shutdown_complete",
        extra={"duration_ms": duration_ms, "timeout_s": SHUTDOWN_TIMEOUT_SECONDS},
    )


# ──────────────────────────────────────────────
# ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ
# ──────────────────────────────────────────────

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    lifespan=lifespan,
)

# CORS — безопасная конфигурация с учётом ENV и credentials
origins = list(settings.ALLOWED_ORIGINS)
if "*" in origins:
    if settings.ENV == "production":
        # В production нельзя молча подменять '*' на сконструированный origin:
        # если PLATFORM_DOMAIN пуст или равен дефолтному "localhost", fallback
        # даст нерабочий/обманчивый origin. Явно падаем, чтобы оператор заметил.
        domain = (settings.PLATFORM_DOMAIN or "").strip().lower()
        if not domain or domain == "localhost":
            raise RuntimeError(
                "ALLOWED_ORIGINS=* is forbidden in production without a real "
                "PLATFORM_DOMAIN. Set ALLOWED_ORIGINS explicitly or configure "
                "PLATFORM_DOMAIN to a real domain."
            )
        origins = [f"https://{domain}"]
        logger.warning(
            "ALLOWED_ORIGINS=* in production, falling back to PLATFORM_DOMAIN "
            f"({settings.PLATFORM_DOMAIN})"
        )
    # в dev оставляем "*", но credentials=False (wildcard несовместим с credentials)
allow_credentials = "*" not in origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info(
    f"CORS configured: origins={origins}, allow_credentials={allow_credentials}, env={settings.ENV}"
)

# Публичный маршрут
@app.get("/healthz")
def health_check():
    return {"status": "ok"}


# ──────────────────────────────────────────────
# READYZ — readiness probe (Шаг 13)
# ──────────────────────────────────────────────

from fastapi import Request
from fastapi.responses import JSONResponse, PlainTextResponse


def _check_db() -> tuple[bool, str]:
    """Проверка доступности БД через SELECT 1."""
    try:
        from sqlalchemy import text

        from app.core.database import db_manager

        engine = getattr(db_manager, "engine", None) or getattr(db_manager, "async_engine", None)
        if engine is None:
            return False, "no engine"
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


@app.get("/readyz", tags=["health"])
def readyz_handler(request: Request):
    """Readiness probe — 200, если все зависимости готовы.

    Проверяет:
      - БД доступна (SELECT 1);
      - Discovery watcher активен (``observer.is_alive()``);
      - Caddy инициализирован.
    Возвращает 503, если хотя бы одна проверка провалилась.
    """
    state = request.app.state
    checks: dict[str, dict[str, str]] = {}
    overall_ok = True

    db_ok, db_msg = _check_db()
    checks["database"] = {"status": "ok" if db_ok else "fail", "detail": db_msg}
    overall_ok = overall_ok and db_ok

    discovery = getattr(state, "discovery", None)
    disc_ok = False
    disc_msg = "not initialized"
    if discovery is not None:
        observer = getattr(discovery, "observer", None)
        if observer is not None:
            is_alive_fn = getattr(observer, "is_alive", None)
            if callable(is_alive_fn):
                disc_ok = bool(is_alive_fn())
                disc_msg = "ok" if disc_ok else "watcher not running"
            else:
                disc_ok = True
                disc_msg = "ok (no is_alive)"
        else:
            disc_msg = "no observer"
    checks["discovery"] = {"status": "ok" if disc_ok else "fail", "detail": disc_msg}
    overall_ok = overall_ok and disc_ok

    caddy_ok = getattr(state, "caddy", None) is not None
    caddy_msg = "ok" if caddy_ok else "caddy not initialized"
    checks["caddy"] = {"status": "ok" if caddy_ok else "fail", "detail": caddy_msg}
    overall_ok = overall_ok and caddy_ok

    body = {
        "status": "ok" if overall_ok else "fail",
        "checks": checks,
        "env": settings.ENV,
        "version": settings.PROJECT_VERSION,
    }
    return JSONResponse(status_code=200 if overall_ok else 503, content=body)


# ──────────────────────────────────────────────
# METRICS — Prometheus-совместимый endpoint (Шаг 13)
# ──────────────────────────────────────────────

_metrics: dict[str, float] = {
    "deploy_total": 0,
    "backup_total": 0,
    "restore_total": 0,
    "services_count": 0,
    "unhealthy_services": 0,
}


def incr_metric(name: str, delta: int = 1) -> None:
    """Увеличивает счётчик метрики (вызывается из background tasks)."""
    if name in _metrics:
        _metrics[name] += delta


def set_gauge(name: str, value: int) -> None:
    """Устанавливает значение gauge (вызывается из background tasks)."""
    if name in _metrics:
        _metrics[name] = value


def _render_prometheus() -> str:
    """Рендерит текущие метрики в формате text/plain Prometheus exposition."""
    lines: list[str] = []
    for name, value in _metrics.items():
        metric_type = "counter" if name.endswith("_total") else "gauge"
        lines.append(f"# TYPE master_{name} {metric_type}")
        lines.append(f"master_{name} {value}")
    return "\n".join(lines) + "\n"


@app.get("/metrics", tags=["health"])
def metrics_endpoint():
    """Prometheus-совместимый endpoint.

    Реализован без зависимости ``prometheus_client`` (минимизация deps).
    Метрики обновляются вручную через ``incr_metric``/``set_gauge``
    и при каждом scrape — gauge ``services_count`` синхронизируется с discovery.
    """
    try:
        state = app.state
        discovery = getattr(state, "discovery", None)
        if discovery is not None:
            services = getattr(discovery, "services", {}) or {}
            set_gauge("services_count", len(services))
    except Exception:  # noqa: BLE001
        # Метрика best-effort — не ломаем /metrics при сбое
        pass

    return PlainTextResponse(
        content=_render_prometheus(),
        media_type="text/plain; version=0.0.4",
    )


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