from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Enum, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import Optional, List
import enum

from app.core.database import BaseModel


class ServiceType(str, enum.Enum):
    """Тип сервиса"""
    DOCKER_COMPOSE = "docker-compose"
    DOCKER = "docker"
    STATIC = "static"
    EXTERNAL = "external"


class ServiceVisibility(str, enum.Enum):
    """Видимость сервиса"""
    PUBLIC = "public"
    INTERNAL = "internal"


class ServiceStatus(str, enum.Enum):
    """Статус сервиса"""
    UNKNOWN = "unknown"
    RUNNING = "running"
    STOPPED = "stopped"
    PARTIAL = "partial"
    ERROR = "error"


class RoutingType(str, enum.Enum):
    """Тип маршрутизации"""
    DOMAIN = "domain"
    SUBFOLDER = "subfolder"
    PORT = "port"


class RoutingConfig(BaseModel):
    """Конфигурация маршрутизации"""
    __tablename__ = "routing_configs"
    
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    type = Column(Enum(RoutingType), nullable=False)
    domain = Column(String(255), nullable=True)
    base_domain = Column(String(255), nullable=True)
    path = Column(String(255), nullable=True)
    port = Column(Integer, nullable=True)
    strip_prefix = Column(Boolean, default=True)
    internal_port = Column(Integer, default=8000)
    headers = Column(JSON, nullable=True)  # Дополнительные заголовки


class HealthConfig(BaseModel):
    """Конфигурация проверки здоровья"""
    __tablename__ = "health_configs"
    
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    enabled = Column(Boolean, default=True)
    endpoint = Column(String(255), default="/health")
    interval = Column(String(50), default="30s")
    timeout = Column(String(50), default="10s")
    retries = Column(Integer, default=3)


class BackupConfig(BaseModel):
    """Конфигурация бэкапов"""
    __tablename__ = "backup_configs"
    
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    enabled = Column(Boolean, default=False)
    schedule = Column(String(100), default="0 2 * * *")
    retention = Column(Integer, default=7)
    paths = Column(JSON, nullable=True)  # Пути для бэкапа
    databases = Column(JSON, nullable=True)  # Конфигурации баз данных


class Service(BaseModel):
    """Модель сервиса"""
    __tablename__ = "services"
    
    name = Column(String(100), unique=True, index=True, nullable=False)
    display_name = Column(String(255), nullable=True)
    version = Column(String(50), default="1.0.0")
    description = Column(Text, nullable=True)
    type = Column(Enum(ServiceType), default=ServiceType.DOCKER_COMPOSE)
    visibility = Column(Enum(ServiceVisibility), default=ServiceVisibility.INTERNAL)
    status = Column(Enum(ServiceStatus), default=ServiceStatus.UNKNOWN)
    tags = Column(JSON, nullable=True)  # Список тегов
    
    # Связи
    routing_configs = relationship("RoutingConfig", backref="service")
    health_config = relationship("HealthConfig", backref="service", uselist=False)
    backup_config = relationship("BackupConfig", backref="service", uselist=False)
    
    def __repr__(self):
        return f"<Service(name='{self.name}', status='{self.status}')>"