"""Тесты для Pydantic-моделей - общие фикстуры и утилиты."""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from typing import Type, Dict, Any


# Общие фикстуры для всех Pydantic-моделей
@pytest.fixture
def sample_datetime():
    """Образец datetime для тестов."""
    return datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def base_service_response_data():
    """Базовые данные для тестирования ServiceResponse."""
    return {
        "name": "test-service",
        "display_name": "Test Service",
        "version": "1.0.0",
        "status": "running",
        "visibility": "public",
        "type": "docker-compose"
    }


@pytest.fixture
def base_log_entry_response_data(sample_datetime):
    """Базовые данные для тестирования LogEntryResponse."""
    return {
        "timestamp": sample_datetime.isoformat(),
        "level": "info",
        "message": "Test log message"
    }


@pytest.fixture
def base_deployment_response_data(sample_datetime):
    """Базовые данные для тестирования DeploymentResponse."""
    return {
        "id": 1,
        "service_id": 1,
        "version": "1.0.0",
        "status": "completed",
        "started_at": sample_datetime,
        "finished_at": sample_datetime,
        "success": True,
        "rollback_available": True
    }


@pytest.fixture
def base_backup_response_data(sample_datetime):
    """Базовые данные для тестирования BackupResponse."""
    return {
        "id": 1,
        "service_id": 1,
        "name": "backup_20240101",
        "timestamp": sample_datetime,
        "size": 1024,
        "status": "completed",
        "reason": "manual"
    }


@pytest.fixture
def base_tls_validation_response_data():
    """Базовые данные для тестирования TLSValidationResponse."""
    return {
        "status": "ok",
        "service": "test-service",
        "domain": "test.example.com"
    }


class ModelTestFixture:
    """Вспомогательный класс для тестирования Pydantic-моделей."""
    
    def __init__(self, model_class: Type, required_fields: Dict[str, Any]):
        self.model_class = model_class
        self.required_fields = required_fields
    
    def create_instance(self, **kwargs) -> Any:
        """Создает экземпляр модели с заданными полями."""
        fields = self.required_fields.copy()
        fields.update(kwargs)
        return self.model_class(**fields)
    
    def validate_required_fields(self, instance: Any) -> bool:
        """Проверяет, что все обязательные поля присутствуют."""
        for field, value in self.required_fields.items():
            if getattr(instance, field) != value:
                return False
        return True
    
    def test_field_types(self, instance: Any, field_types: Dict[str, type]) -> bool:
        """Проверяет типы полей."""
        for field, expected_type in field_types.items():
            if not isinstance(getattr(instance, field), expected_type):
                return False
        return True


@pytest.fixture
def model_test_fixture():
    """Фикстура для создания тестовых оберток модели."""
    return ModelTestFixture