"""Тесты для модели резервной копии."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from app.models.backup import Backup, BackupSchedule, RestoreJob
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
def sample_backup(sample_service):
    """Фикстура для создания тестовой резервной копии."""
    return Backup(
        id=1,
        service_id=1,
        name="test-backup-2023-01-01",
        timestamp=datetime(2023, 1, 1, 12, 0, 0),
        size=1024,
        status="created",
        reason="manual",
        path="/backups/test-backup-2023-01-01.tar.gz",
        metadata_json='{"version": "1.0.0"}'
    )


@pytest.fixture
def sample_backup_schedule(sample_service):
    """Фикстура для создания тестового расписания бэкапов."""
    return BackupSchedule(
        id=1,
        service_id=1,
        cron_expression="0 2 * * *",
        enabled=True,
        retention_days=7
    )


@pytest.fixture
def sample_restore_job(sample_backup, sample_service):
    """Фикстура для создания тестового задания восстановления."""
    return RestoreJob(
        id=1,
        backup_id=1,
        service_id=1,
        status="pending",
        started_at=datetime(2023, 1, 1, 12, 0, 0),
        logs="Restore job started",
        success=False
    )


def test_backup_creation(db_session, sample_service, sample_backup):
    """Тест создания резервной копии."""
    # Добавляем сервис и бэкап в базу
    db_session.add(sample_service)
    db_session.add(sample_backup)
    db_session.commit()
    db_session.refresh(sample_backup)
    
    # Проверяем, что бэкап был сохранен
    assert sample_backup.id is not None
    assert sample_backup.service_id == 1
    assert sample_backup.name == "test-backup-2023-01-01"
    assert sample_backup.timestamp == datetime(2023, 1, 1, 12, 0, 0)
    assert sample_backup.size == 1024
    assert sample_backup.status == "created"
    assert sample_backup.reason == "manual"
    assert sample_backup.path == "/backups/test-backup-2023-01-01.tar.gz"
    assert sample_backup.metadata_json == '{"version": "1.0.0"}'


def test_backup_schedule_creation(db_session, sample_service, sample_backup_schedule):
    """Тест создания расписания бэкапов."""
    # Добавляем сервис и расписание в базу
    db_session.add(sample_service)
    db_session.add(sample_backup_schedule)
    db_session.commit()
    db_session.refresh(sample_backup_schedule)
    
    # Проверяем атрибуты
    assert sample_backup_schedule.id is not None
    assert sample_backup_schedule.service_id == 1
    assert sample_backup_schedule.cron_expression == "0 2 * * *"
    assert sample_backup_schedule.enabled is True
    assert sample_backup_schedule.retention_days == 7


def test_restore_job_creation(db_session, sample_backup, sample_service, sample_restore_job):
    """Тест создания задания восстановления."""
    # Добавляем все объекты в базу
    db_session.add(sample_service)
    db_session.add(sample_backup)
    db_session.add(sample_restore_job)
    db_session.commit()
    db_session.refresh(sample_restore_job)
    
    # Проверяем атрибуты
    assert sample_restore_job.id is not None
    assert sample_restore_job.backup_id == 1
    assert sample_restore_job.service_id == 1
    assert sample_restore_job.status == "pending"
    assert sample_restore_job.started_at == datetime(2023, 1, 1, 12, 0, 0)
    assert sample_restore_job.logs == "Restore job started"
    assert sample_restore_job.success is False
    assert sample_restore_job.finished_at is None


def test_backup_relationships(db_session, sample_service, sample_backup, 
                              sample_backup_schedule, sample_restore_job):
    """Тест связей бэкапа с другими моделями."""
    # Добавляем все объекты в базу
    db_session.add(sample_service)
    db_session.add(sample_backup)
    db_session.add(sample_backup_schedule)
    db_session.add(sample_restore_job)
    db_session.commit()
    
    # Обновляем объекты, чтобы получить связи
    db_session.refresh(sample_backup)
    db_session.refresh(sample_service)
    
    # Проверяем связи
    assert sample_backup.service is not None
    assert sample_backup.service.name == "test-service"
    assert len(sample_backup.restore_jobs) == 1
    assert sample_backup.restore_jobs[0].status == "pending"


def test_backup_schedule_relationships(db_session, sample_service, sample_backup_schedule):
    """Тест связей расписания бэкапов."""
    # Добавляем объекты в базу
    db_session.add(sample_service)
    db_session.add(sample_backup_schedule)
    db_session.commit()
    
    # Обновляем объекты, чтобы получить связи
    db_session.refresh(sample_backup_schedule)
    db_session.refresh(sample_service)
    
    # Проверяем связи
    assert sample_backup_schedule.service is not None
    assert sample_backup_schedule.service.name == "test-service"


def test_restore_job_relationships(db_session, sample_backup, sample_service, sample_restore_job):
    """Тест связей задания восстановления."""
    # Добавляем все объекты в базу
    db_session.add(sample_service)
    db_session.add(sample_backup)
    db_session.add(sample_restore_job)
    db_session.commit()
    
    # Обновляем объекты, чтобы получить связи
    db_session.refresh(sample_restore_job)
    
    # Проверяем связи
    assert sample_restore_job.backup is not None
    assert sample_restore_job.backup.name == "test-backup-2023-01-01"
    assert sample_restore_job.service is not None
    assert sample_restore_job.service.name == "test-service"


def test_backup_serialization(sample_backup):
    """Тест сериализации резервной копии."""
    # Проверяем, что у бэкапа есть атрибуты
    assert hasattr(sample_backup, 'id')
    assert hasattr(sample_backup, 'service_id')
    assert hasattr(sample_backup, 'name')
    assert hasattr(sample_backup, 'timestamp')
    assert hasattr(sample_backup, 'size')
    assert hasattr(sample_backup, 'status')
    assert hasattr(sample_backup, 'reason')
    assert hasattr(sample_backup, 'path')
    assert hasattr(sample_backup, 'metadata_json')
    assert hasattr(sample_backup, 'service')
    assert hasattr(sample_backup, 'restore_jobs')


def test_backup_schedule_serialization(sample_backup_schedule):
    """Тест сериализации расписания бэкапов."""
    # Проверяем, что у расписания есть атрибуты
    assert hasattr(sample_backup_schedule, 'id')
    assert hasattr(sample_backup_schedule, 'service_id')
    assert hasattr(sample_backup_schedule, 'cron_expression')
    assert hasattr(sample_backup_schedule, 'enabled')
    assert hasattr(sample_backup_schedule, 'retention_days')
    assert hasattr(sample_backup_schedule, 'service')


def test_restore_job_serialization(sample_restore_job):
    """Тест сериализации задания восстановления."""
    # Проверяем, что у задания есть атрибуты
    assert hasattr(sample_restore_job, 'id')
    assert hasattr(sample_restore_job, 'backup_id')
    assert hasattr(sample_restore_job, 'service_id')
    assert hasattr(sample_restore_job, 'status')
    assert hasattr(sample_restore_job, 'started_at')
    assert hasattr(sample_restore_job, 'finished_at')
    assert hasattr(sample_restore_job, 'logs')
    assert hasattr(sample_restore_job, 'success')
    assert hasattr(sample_restore_job, 'backup')
    assert hasattr(sample_restore_job, 'service')