
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from typing import Generator, AsyncGenerator
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Создание синхронного движка с оптимизациями под SQLite (если используется)
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    echo=False,  # Включить для отладки SQL-запросов
    pool_pre_ping=True,  # Проверка соединения перед использованием
)

# Создание асинхронного движка (только для PostgreSQL с asyncpg, для SQLite используем aiosqlite)
async_engine = None
if settings.DATABASE_URL.startswith("postgresql"):
    # Заменяем postgresql:// на postgresql+asyncpg://
    async_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    async_engine = create_async_engine(
        async_url,
        echo=False,
        pool_pre_ping=True,
    )
elif settings.DATABASE_URL.startswith("sqlite"):
    # Для SQLite используем aiosqlite
    async_url = settings.DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://", 1)
    async_engine = create_async_engine(
        async_url,
        echo=False,
        connect_args={"check_same_thread": False},
    )
else:
    logger.warning(f"Async engine not configured for DATABASE_URL: {settings.DATABASE_URL}")

_base = None

def get_base():
    global _base
    if _base is None:
        _base = declarative_base()
    return _base

Base = get_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False) if async_engine else None


class DatabaseManager:
    """Менеджер базы данных с улучшенной обработкой ошибок и логированием."""

    def __init__(self):
        self.engine = engine
        self.SessionLocal = SessionLocal
        self.Base = get_base()  # Используем функцию для получения базы

    def create_tables(self) -> None:
        """Создаёт все таблицы, если они ещё не существуют."""
        try:
            self.Base.metadata.create_all(bind=self.engine)
            logger.info("Таблицы базы данных успешно созданы или уже существуют.")
        except Exception as e:
            logger.error(f"Ошибка при создании таблиц: {e}")
            raise

    def get_db(self) -> Generator[Session, None, None]:
        """Генератор сессии базы данных для использования в FastAPI."""
        db = self.SessionLocal()
        try:
            yield db
        except Exception as e:
            db.rollback()
            logger.error(f"Ошибка в транзакции БД: {e}")
            raise
        finally:
            db.close()

    async def get_async_db(self) -> AsyncGenerator[AsyncSession, None]:
        """Асинхронный генератор сессии базы данных."""
        if not async_engine:
            raise RuntimeError("Async engine not configured")
        async with AsyncSessionLocal() as session:
            try:
                yield session
            except Exception as e:
                await session.rollback()
                logger.error(f"Ошибка в асинхронной транзакции БД: {e}")
                raise


db_manager = DatabaseManager()


# Зависимость для внедрения сессии БД
def get_db() -> Generator[Session, None, None]:
    """Зависимость FastAPI для получения сессии базы данных."""
    yield from db_manager.get_db()


# Асинхронная зависимость для внедрения сессии БД
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Асинхронная зависимость FastAPI для получения сессии базы данных."""
    async for session in db_manager.get_async_db():
        yield session


# Отложенная загрузка моделей — чтобы Base была доступна
# init_models() больше не нужна, так как модели инициализируются через get_base() при определении классов.