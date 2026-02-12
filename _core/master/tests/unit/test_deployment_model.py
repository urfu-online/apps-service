"""Тесты для модели развертывания."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from app.models.deployment import Deployment, DeploymentLog
from app.models.service import Service
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
        description="A test service"
    )


@pytest.fixture
def sample_deployment(sample_service):
    """Фикстура для создания тестового развертывания."""
    return Deployment(
        id=1,
        service_id=1,
        version="1.0.0",
        status="pending",
        started_at=datetime(2023, 1, 1, 12, 0, 0),
        logs="Deployment started",
        success=False,
        rollback_available=False
    )


@pytest.fixture
def sample_deployment_log(sample_deployment):
    """Фикстура для создания тестового лога развертывания."""
    return DeploymentLog(
        id=1,
        deployment_id=1,
        level="info",
        message="Deployment process started",
        timestamp=datetime(2023, 1, 1, 12, 0, 0)
    )


def test_deployment_creation(db_session, sample_service, sample_deployment):
    """Тест создания развертывания."""
    # Добавляем сервис и развертывание в базу
    db_session.add(sample_service)
    db_session.add(sample_deployment)
    db_session.commit()
    db_session.refresh(sample_deployment)
    
    # Проверяем, что развертывание было сохранено
    assert sample_deployment.id is not None
    assert sample_deployment.service_id == 1
    assert sample_deployment.version == "1.0.0"
    assert sample_deployment.status == "pending"
    assert sample_deployment.started_at == datetime(2023, 1, 1, 12, 0, 0)
    assert sample_deployment.logs == "Deployment started"
    assert sample_deployment.success is False
    assert sample_deployment.rollback_available is False
    assert sample_deployment.finished_at is None


def test_deployment_log_creation(db_session, sample_deployment, sample_deployment_log):
    """Тест создания лога развертывания."""
    # Добавляем развертывание и лог в базу
    db_session.add(sample_deployment)
    db_session.add(sample_deployment_log)
    db_session.commit()
    db_session.refresh(sample_deployment_log)
    
    # Проверяем атрибуты
    assert sample_deployment_log.id is not None
    assert sample_deployment_log.deployment_id == 1
    assert sample_deployment_log.level == "info"
    assert sample_deployment_log.message == "Deployment process started"
    assert sample_deployment_log.timestamp == datetime(2023, 1, 1, 12, 0, 0)


def test_deployment_relationships(db_session, sample_service, sample_deployment, 
                                sample_deployment_log):
    """Тест связей развертывания."""
    # Добавляем все объекты в базу
    db_session.add(sample_service)
    db_session.add(sample_deployment)
    db_session.add(sample_deployment_log)
    db_session.commit()
    
    # Обновляем объекты, чтобы получить связи
    db_session.refresh(sample_deployment)
    db_session.refresh(sample_service)
    
    # Проверяем связи
    assert sample_deployment.service is not None
    assert sample_deployment.service.name == "test-service"
    assert len(sample_deployment.logs) == 1
    assert sample_deployment.logs[0].message == "Deployment process started"


def test_deployment_log_relationships(db_session, sample_deployment, sample_deployment_log):
    """Тест связей лога развертывания."""
    # Добавляем объекты в базу
    db_session.add(sample_deployment)
    db_session.add(sample_deployment_log)
    db_session.commit()
    
    # Обновляем объекты, чтобы получить связи
    db_session.refresh(sample_deployment_log)
    
    # Проверяем связи
    assert sample_deployment_log.deployment is not None
    assert sample_deployment_log.deployment.version == "1.0.0"


def test_deployment_serialization(sample_deployment):
    """Тест сериализации развертывания."""
    # Проверяем, что у развертывания есть атрибуты
    assert hasattr(sample_deployment, 'id')
    assert hasattr(sample_deployment, 'service_id')
    assert hasattr(sample_deployment, 'version')
    assert hasattr(sample_deployment, 'status')
    assert hasattr(sample_deployment, 'started_at')
    assert hasattr(sample_deployment, 'finished_at')
    assert hasattr(sample_deployment, 'logs')
    assert hasattr(sample_deployment, 'success')
    assert hasattr(sample_deployment, 'rollback_available')
    assert hasattr(sample_deployment, 'service')


def test_deployment_log_serialization(sample_deployment_log):
    """Тест сериализации лога развертывания."""
    # Проверяем, что у лога есть атрибуты
    assert hasattr(sample_deployment_log, 'id')
    assert hasattr(sample_deployment_log, 'deployment_id')
    assert hasattr(sample_deployment_log, 'level')
    assert hasattr(sample_deployment_log, 'message')
    assert hasattr(sample_deployment_log, 'timestamp')
    assert hasattr(sample_deployment_log, 'deployment')


def test_deployment_status_updates(db_session, sample_service, sample_deployment):
    """Тест обновления статуса развертывания."""
    # Добавляем сервис и развертывание в базу
    db_session.add(sample_service)
    db_session.add(sample_deployment)
    db_session.commit()
    
    # Обновляем статус развертывания
    sample_deployment.status = "running"
    sample_deployment.success = False
    db_session.commit()
    db_session.refresh(sample_deployment)
    
    # Проверяем обновление
    assert sample_deployment.status == "running"
    assert sample_deployment.success is False
    
    # Завершаем развертывание
    sample_deployment.status = "completed"
    sample_deployment.success = True
    sample_deployment.finished_at = datetime(2023, 1, 1, 12, 5, 0)
    db_session.commit()
    db_session.refresh(sample_deployment)
    
    # Проверяем завершение
    assert sample_deployment.status == "completed"
    assert sample_deployment.success is True
    assert sample_deployment.finished_at == datetime(2023, 1, 1, 12, 5, 0)


def test_deployment_log_levels(sample_deployment_log):
    """Тест различных уровней логов развертывания."""
    # Проверяем различные уровни логов
    assert sample_deployment_log.level == "info"
    
    # Создаем лог с уровнем warning
    warning_log = DeploymentLog(
        id=2,
        deployment_id=1,
        level="warning",
        message="This is a warning message",
        timestamp=datetime(2023, 1, 1, 12, 1, 0)
    )
    
    assert warning_log.level == "warning"
    
    # Создаем лог с уровнем error
    error_log = DeploymentLog(
        id=3,
        deployment_id=1,
        level="error",
        message="This is an error message",
        timestamp=datetime(2023, 1, 1, 12, 2, 0)
    )
    
    assert error_log.level == "error"