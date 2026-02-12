from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import Optional

from app.core.database import BaseModel


class Backup(BaseModel):
    """Модель бэкапа"""
    __tablename__ = "backups"
    
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    name = Column(String(255), unique=True, index=True, nullable=False)  # Имя бэкапа
    timestamp = Column(DateTime, default=datetime.utcnow)  # Время создания
    size = Column(Integer, nullable=True)  # Размер в байтах
    status = Column(String(50), default="created")  # Статус бэкапа
    reason = Column(String(100), default="manual")  # Причина создания (manual, scheduled, auto)
    path = Column(String(500), nullable=True)  # Путь к бэкапу
    metadata_json = Column(Text, nullable=True)  # Метаданные в формате JSON
    
    # Связи
    service = relationship("Service", backref="backups")
    
    def __repr__(self):
        return f"<Backup(service_id={self.service_id}, name='{self.name}', status='{self.status}')>"
    
    
class BackupSchedule(BaseModel):
    """Расписание бэкапов"""
    __tablename__ = "backup_schedules"
    
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    cron_expression = Column(String(100), nullable=False)  # CRON выражение
    enabled = Column(Boolean, default=True)  # Активность расписания
    retention_days = Column(Integer, default=7)  # Время хранения в днях
    
    # Связи
    service = relationship("Service", backref="backup_schedules")
    
    def __repr__(self):
        return f"<BackupSchedule(service_id={self.service_id}, cron='{self.cron_expression}')>"
    
    
class RestoreJob(BaseModel):
    """Задание на восстановление"""
    __tablename__ = "restore_jobs"
    
    backup_id = Column(Integer, ForeignKey("backups.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    status = Column(String(50), default="pending")  # Статус восстановления
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    logs = Column(Text, nullable=True)  # Логи восстановления
    success = Column(Boolean, default=False)  # Успешность восстановления
    
    # Связи
    backup = relationship("Backup", backref="restore_jobs")
    service = relationship("Service", backref="restore_jobs")
    
    def __repr__(self):
        return f"<RestoreJob(backup_id={self.backup_id}, status='{self.status}')>"