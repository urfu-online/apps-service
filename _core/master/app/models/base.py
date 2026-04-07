from sqlalchemy import Column, Integer, DateTime, Boolean
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone

from app.core.database import get_base

Base = get_base()


class BaseModel(Base):
    """Базовая модель с общими полями."""
    __abstract__ = True

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)
