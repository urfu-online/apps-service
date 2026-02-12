from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import Optional

from app.core.database import BaseModel


class Deployment(BaseModel):
    """Модель деплоя сервиса"""
    __tablename__ = "deployments"
    
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    version = Column(String(50), nullable=False)  # Версия сервиса при деплое
    status = Column(String(50), default="pending")  # Статус деплоя
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    logs = Column(Text, nullable=True)  # Логи деплоя
    success = Column(Boolean, default=False)  # Успешность деплоя
    rollback_available = Column(Boolean, default=False)  # Доступность отката
    
    # Связи
    service = relationship("Service", backref="deployments")
    
    def __repr__(self):
        return f"<Deployment(service_id={self.service_id}, version='{self.version}', status='{self.status}')>"
    
    
class DeploymentLog(BaseModel):
    """Логи деплоя"""
    __tablename__ = "deployment_logs"
    
    deployment_id = Column(Integer, ForeignKey("deployments.id"), nullable=False)
    level = Column(String(20), default="info")  # Уровень лога (info, warning, error)
    message = Column(Text, nullable=False)  # Сообщение
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    deployment = relationship("Deployment", backref="logs")
    
    def __repr__(self):
        return f"<DeploymentLog(deployment_id={self.deployment_id}, level='{self.level}')>"