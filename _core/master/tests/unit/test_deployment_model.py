"""Тесты для модели развертывания."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone
from app.models.deployment import Deployment, DeploymentLog
from app.models.service import Service
from app.core.database import Base


@pytest.fixture
def db_session():
    """Фикстура для создания тестовой базы данных."""
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
def sample_deployment():
    """Фикстура для создания тестового развертывания."""
    return Deployment(
        id=1,
        service_id=1,
        version="1.0.0",
        status="pending",
        started_at=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        logs="Deployment started",
        success=False,
        rollback_available=False
    )


@pytest.fixture
def sample_deployment_log():
    """Фикстура для создания тестового лога развертывания."""
    return DeploymentLog(
        id=1,
        deployment_id=1,
        level="info",
        message="Deployment process started",
        timestamp=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    )


def test_deployment_creation(db_session, sample_service, sample_deployment):
    """Тест создания развертывания."""
    db_session.add(sample_service)
    db_session.add(sample_deployment)
    db_session.commit()
    db_session.refresh(sample_deployment)

    assert sample_deployment.id is not None
    assert sample_deployment.service_id == 1
    assert sample_deployment.version == "1.0.0"
    assert sample_deployment.status == "pending"
    assert sample_deployment.success is False
    assert sample_deployment.rollback_available is False
    assert sample_deployment.finished_at is None
    # Добавлены проверки бизнес-логики
    assert sample_deployment.logs == "Deployment started"
    assert sample_deployment.started_at.year == 2023
    assert sample_deployment.started_at.month == 1
    assert sample_deployment.started_at.day == 1


def test_deployment_log_creation(db_session, sample_deployment_log):
    """Тест создания лога развертывания."""
    db_session.add(sample_deployment_log)
    db_session.commit()
    db_session.refresh(sample_deployment_log)

    assert sample_deployment_log.id is not None
    assert sample_deployment_log.deployment_id == 1
    assert sample_deployment_log.level == "info"
    assert sample_deployment_log.message == "Deployment process started"
    # Добавлены проверки бизнес-логики
    assert sample_deployment_log.timestamp.year == 2023
    assert sample_deployment_log.timestamp.month == 1
    assert sample_deployment_log.timestamp.day == 1


def test_deployment_service_relationship(db_session, sample_service, sample_deployment):
    """Тест связи развертывания с сервисом."""
    db_session.add(sample_service)
    db_session.add(sample_deployment)
    db_session.commit()

    db_session.refresh(sample_deployment)

    assert sample_deployment.service is not None
    assert sample_deployment.service.name == "test-service"


def test_deployment_log_relationship(db_session, sample_deployment, sample_deployment_log):
    """Тест связи лога с развертыванием."""
    db_session.add(sample_deployment)
    db_session.add(sample_deployment_log)
    db_session.commit()

    db_session.refresh(sample_deployment_log)

    assert sample_deployment_log.deployment is not None
    assert sample_deployment_log.deployment.version == "1.0.0"


def test_deployment_deployment_logs_relationship(db_session, sample_service, sample_deployment, sample_deployment_log):
    """Тест обратной связи развертывания с логами."""
    db_session.add(sample_service)
    db_session.add(sample_deployment)
    db_session.add(sample_deployment_log)
    db_session.commit()

    db_session.refresh(sample_deployment)

    # backref называется deployment_logs (не logs, т.к. logs - это Column)
    assert hasattr(sample_deployment, 'deployment_logs')
    assert len(sample_deployment.deployment_logs) == 1
    assert sample_deployment.deployment_logs[0].message == "Deployment process started"


def test_deployment_serialization(sample_deployment):
    """Тест сериализации развертывания."""
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
    assert hasattr(sample_deployment_log, 'id')
    assert hasattr(sample_deployment_log, 'deployment_id')
    assert hasattr(sample_deployment_log, 'level')
    assert hasattr(sample_deployment_log, 'message')
    assert hasattr(sample_deployment_log, 'timestamp')
    assert hasattr(sample_deployment_log, 'deployment')


def test_deployment_status_updates(db_session, sample_service, sample_deployment):
    """Тест обновления статуса развертывания."""
    db_session.add(sample_service)
    db_session.add(sample_deployment)
    db_session.commit()

    sample_deployment.status = "running"
    db_session.commit()
    db_session.refresh(sample_deployment)

    assert sample_deployment.status == "running"
    # Добавлена дополнительная проверка бизнес-логики
    assert sample_deployment.success is False  # Даже в состоянии running успех еще не достигнут

    sample_deployment.status = "completed"
    sample_deployment.success = True
    sample_deployment.rollback_available = True  # Устанавливаем явно, так как по умолчанию False
    sample_deployment.finished_at = datetime(2023, 1, 1, 12, 5, 0, tzinfo=timezone.utc)
    sample_deployment.logs = "Deployment completed successfully"
    db_session.commit()
    db_session.refresh(sample_deployment)

    assert sample_deployment.status == "completed"
    assert sample_deployment.success is True
    assert sample_deployment.rollback_available is True  # Проверяем, что откат доступен
    assert sample_deployment.finished_at is not None
    # Добавлена дополнительная проверка бизнес-логики
    assert "completed successfully" in sample_deployment.logs


def test_deployment_log_levels():
    """Тест различных уровней логов развертывания."""
    timestamp = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    
    info_log = DeploymentLog(
        deployment_id=1,
        level="info",
        message="Info message",
        timestamp=timestamp
    )
    assert info_log.level == "info"
    # Бизнес-логика: уровень лога имеет допустимые значения
    assert info_log.level in ["info", "warning", "error", "debug"]

    warning_log = DeploymentLog(
        deployment_id=1,
        level="warning",
        message="Warning message",
        timestamp=timestamp
    )
    assert warning_log.level == "warning"
    assert warning_log.message == "Warning message"

    error_log = DeploymentLog(
        deployment_id=1,
        level="error",
        message="Error message",
        timestamp=timestamp
    )
    assert error_log.level == "error"
    # Бизнес-логика: ошибки требуют внимания
    assert "Error" in error_log.message
