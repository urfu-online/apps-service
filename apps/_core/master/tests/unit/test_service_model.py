"""Тесты для модели сервиса."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from app.models.service import (
    Service, ServiceType, ServiceVisibility, ServiceStatus,
    RoutingType, RoutingConfig, HealthConfig, BackupConfig
)
from app.core.database import Base


@pytest.fixture
def db_session():
    """Фикстура для создания тестовой базы данных."""
    # Создаем in-memory SQLite базу для тестов
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    yield session
    
    session.close()


@pytest.fixture
def sample_service():
    """Фикстура для создания тестового сервиса."""
    return Service(
        id=1,
        name="test-service",
        display_name="Test Service",
        version="1.0.0",
        description="A test service",
        type=ServiceType.DOCKER_COMPOSE,
        visibility=ServiceVisibility.INTERNAL,
        status=ServiceStatus.UNKNOWN
    )


@pytest.fixture
def sample_routing_config():
    """Фикстура для создания тестовой конфигурации маршрутизации."""
    return RoutingConfig(
        id=1,
        service_id=1,
        type=RoutingType.DOMAIN,
        domain="test.example.com",
        internal_port=8000
    )


@pytest.fixture
def sample_health_config():
    """Фикстура для создания тестовой конфигурации здоровья."""
    return HealthConfig(
        id=1,
        service_id=1,
        enabled=True,
        endpoint="/health",
        interval="30s",
        timeout="10s",
        retries=3
    )


@pytest.fixture
def sample_backup_config():
    """Фикстура для создания тестовой конфигурации бэкапа."""
    return BackupConfig(
        id=1,
        service_id=1,
        enabled=True,
        schedule="0 2 * * *",
        retention=7
    )


def test_service_creation(db_session, sample_service):
    """Тест создания сервиса."""
    # Добавляем сервис в базу
    db_session.add(sample_service)
    db_session.commit()
    db_session.refresh(sample_service)
    
    # Проверяем, что сервис был сохранен
    assert sample_service.id is not None
    assert sample_service.name == "test-service"
    assert sample_service.display_name == "Test Service"
    assert sample_service.version == "1.0.0"
    assert sample_service.description == "A test service"
    assert sample_service.type == ServiceType.DOCKER_COMPOSE
    assert sample_service.visibility == ServiceVisibility.INTERNAL
    assert sample_service.status == ServiceStatus.UNKNOWN


def test_service_type_enum():
    """Тест перечисления типов сервисов."""
    assert ServiceType.DOCKER_COMPOSE == "docker-compose"
    assert ServiceType.DOCKER == "docker"
    assert ServiceType.STATIC == "static"
    assert ServiceType.EXTERNAL == "external"


def test_service_visibility_enum():
    """Тест перечисления видимости сервисов."""
    assert ServiceVisibility.PUBLIC == "public"
    assert ServiceVisibility.INTERNAL == "internal"


def test_service_status_enum():
    """Тест перечисления статусов сервисов."""
    assert ServiceStatus.UNKNOWN == "unknown"
    assert ServiceStatus.RUNNING == "running"
    assert ServiceStatus.STOPPED == "stopped"
    assert ServiceStatus.PARTIAL == "partial"
    assert ServiceStatus.ERROR == "error"


def test_routing_config_creation(db_session, sample_routing_config):
    """Тест создания конфигурации маршрутизации."""
    # Добавляем конфигурацию в базу
    db_session.add(sample_routing_config)
    db_session.commit()
    db_session.refresh(sample_routing_config)
    
    # Проверяем атрибуты
    assert sample_routing_config.id is not None
    assert sample_routing_config.service_id == 1
    assert sample_routing_config.type == RoutingType.DOMAIN
    assert sample_routing_config.domain == "test.example.com"
    assert sample_routing_config.internal_port == 8000


def test_routing_type_enum():
    """Тест перечисления типов маршрутизации."""
    assert RoutingType.DOMAIN == "domain"
    assert RoutingType.SUBFOLDER == "subfolder"
    assert RoutingType.PORT == "port"


def test_health_config_creation(db_session, sample_health_config):
    """Тест создания конфигурации здоровья."""
    # Добавляем конфигурацию в базу
    db_session.add(sample_health_config)
    db_session.commit()
    db_session.refresh(sample_health_config)
    
    # Проверяем атрибуты
    assert sample_health_config.id is not None
    assert sample_health_config.service_id == 1
    assert sample_health_config.enabled is True
    assert sample_health_config.endpoint == "/health"
    assert sample_health_config.interval == "30s"
    assert sample_health_config.timeout == "10s"
    assert sample_health_config.retries == 3


def test_backup_config_creation(db_session, sample_backup_config):
    """Тест создания конфигурации бэкапа."""
    # Добавляем конфигурацию в базу
    db_session.add(sample_backup_config)
    db_session.commit()
    db_session.refresh(sample_backup_config)
    
    # Проверяем атрибуты
    assert sample_backup_config.id is not None
    assert sample_backup_config.service_id == 1
    assert sample_backup_config.enabled is True
    assert sample_backup_config.schedule == "0 2 * * *"
    assert sample_backup_config.retention == 7


def test_service_relationships(db_session, sample_service, sample_routing_config, 
                              sample_health_config, sample_backup_config):
    """Тест связей сервиса с конфигурациями."""
    # Добавляем все объекты в базу
    db_session.add(sample_service)
    db_session.add(sample_routing_config)
    db_session.add(sample_health_config)
    db_session.add(sample_backup_config)
    db_session.commit()
    
    # Обновляем сервис, чтобы получить связи
    db_session.refresh(sample_service)
    
    # Проверяем связи
    assert len(sample_service.routing_configs) == 1
    assert sample_service.health_config is not None
    assert sample_service.backup_config is not None


def test_service_serialization(sample_service):
    """Тест сериализации сервиса."""
    # Проверяем, что у сервиса есть атрибуты
    assert hasattr(sample_service, 'id')
    assert hasattr(sample_service, 'name')
    assert hasattr(sample_service, 'display_name')
    assert hasattr(sample_service, 'version')
    assert hasattr(sample_service, 'description')
    assert hasattr(sample_service, 'type')
    assert hasattr(sample_service, 'visibility')
    assert hasattr(sample_service, 'status')
    assert hasattr(sample_service, 'routing_configs')
    assert hasattr(sample_service, 'health_config')
    assert hasattr(sample_service, 'backup_config')


def test_routing_config_serialization(sample_routing_config):
    """Тест сериализации конфигурации маршрутизации."""
    # Проверяем, что у конфигурации есть атрибуты
    assert hasattr(sample_routing_config, 'id')
    assert hasattr(sample_routing_config, 'service_id')
    assert hasattr(sample_routing_config, 'type')
    assert hasattr(sample_routing_config, 'domain')
    assert hasattr(sample_routing_config, 'internal_port')


def test_health_config_serialization(sample_health_config):
    """Тест сериализации конфигурации здоровья."""
    # Проверяем, что у конфигурации есть атрибуты
    assert hasattr(sample_health_config, 'id')
    assert hasattr(sample_health_config, 'service_id')
    assert hasattr(sample_health_config, 'enabled')
    assert hasattr(sample_health_config, 'endpoint')
    assert hasattr(sample_health_config, 'interval')
    assert hasattr(sample_health_config, 'timeout')
    assert hasattr(sample_health_config, 'retries')


def test_backup_config_serialization(sample_backup_config):
    """Тест сериализации конфигурации бэкапа."""
    # Проверяем, что у конфигурации есть атрибуты
    assert hasattr(sample_backup_config, 'id')
    assert hasattr(sample_backup_config, 'service_id')
    assert hasattr(sample_backup_config, 'enabled')
    assert hasattr(sample_backup_config, 'schedule')
    assert hasattr(sample_backup_config, 'retention')