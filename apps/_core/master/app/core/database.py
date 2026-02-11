from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from typing import Optional
import logging

from app.config import settings

# Настройка логирования
logger = logging.getLogger(__name__)

# Создание движка базы данных
engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})

# Создание базового класса для моделей
Base = declarative_base()

# Создание сессии
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class DatabaseManager:
    """Менеджер базы данных"""
    
    def __init__(self):
        self.engine = engine
        self.SessionLocal = SessionLocal
        self.Base = Base
    
    def create_tables(self):
        """Создание всех таблиц"""
        try:
            # Создание всех таблиц
            self.Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating database tables: {e}")
            raise
    
    def get_db(self):
        """Получение сессии базы данных"""
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()


# Глобальный экземпляр менеджера базы данных
db_manager = DatabaseManager()


# Базовая модель с общими полями
class BaseModel(Base):
    __abstract__ = True
    
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)


# Импорт моделей для создания таблиц
from app.models import user


# Зависимость для получения сессии базы данных
def get_db():
    """Зависимость FastAPI для получения сессии базы данных"""
    db = db_manager.SessionLocal()
    try:
        yield db
    finally:
        db.close()