"""Тесты для endpoints сервисов.

Примечание: Полные endpoint тесты через TestClient не работают из-за NiceGUI инициализации.
Тестируем роутеры напрямую с моками.
"""
import pytest
from unittest.mock import Mock, MagicMock, AsyncMock
from app.services.discovery import ServiceManifest
from .test_model_utils import ModelTestFixture


class TestServiceRoutes:
    """Тесты для routes сервисов (unit tests без TestClient)."""

    def test_service_response_model(self, mock_service_manifest, base_service_response_data):
        """Тест модели ответа сервиса."""
        from app.api.routes.services import ServiceResponse

        response = ServiceResponse(**base_service_response_data)
        assert response.name == "test-service"
        assert response.version == "1.0.0"
        assert response.visibility == "public"
        assert hasattr(response, 'name')
        assert hasattr(response, 'version')
        assert hasattr(response, 'visibility')

    def test_service_response_optional_fields(self, mock_service_manifest):
        """Тест модели ответа сервиса с опциональными полями."""
        from app.api.routes.services import ServiceResponse

        response = ServiceResponse(
            name="minimal-service",
            display_name=None,
            version="1.0.0",
            status="unknown",
            visibility="internal",
            type="docker-compose",
        )

        assert response.name == "minimal-service"
        assert response.display_name is None

    def test_deploy_request_model(self):
        """Тест модели запроса деплоя."""
        from app.api.routes.services import DeployRequest

        request = DeployRequest(build=True, pull=False)
        assert request.build is True
        assert request.pull is False


class TestSharedModelTests:
    """Объединенные тесты Pydantic-моделей из разных файлов."""
    
    def test_log_entry_response_shared(self, base_log_entry_response_data):
        """Тест модели LogEntryResponse из test_log_endpoints."""
        from app.api.routes.logs import LogEntryResponse
        
        required_fields = {
            "timestamp": base_log_entry_response_data["timestamp"],
            "level": base_log_entry_response_data["level"],
            "message": base_log_entry_response_data["message"]
        }
        
        model_fixture = ModelTestFixture(LogEntryResponse, required_fields)
        response = model_fixture.create_instance()
        
        assert model_fixture.validate_required_fields(response)
        assert response.level == "info"
        assert response.message == "Test log message"
    
    def test_log_search_request_shared(self):
        """Тест модели LogSearchRequest из test_log_endpoints."""
        from app.api.routes.logs import LogSearchRequest

        request = LogSearchRequest(query="error", limit=100)
        assert request.query == "error"
        assert request.limit == 100

    def test_log_search_request_default_limit(self):
        """Тест дефолтного лимита LogSearchRequest из test_log_endpoints."""
        from app.api.routes.logs import LogSearchRequest

        request = LogSearchRequest(query="test")
        assert request.limit == 100
        
    def test_deployment_response_shared(self, base_deployment_response_data):
        """Тест модели DeploymentResponse из test_deployment_endpoints."""
        from app.api.routes.deployments import DeploymentResponse

        required_fields = {
            "id": base_deployment_response_data["id"],
            "service_id": base_deployment_response_data["service_id"],
            "version": base_deployment_response_data["version"],
            "status": base_deployment_response_data["status"],
            "started_at": base_deployment_response_data["started_at"],
            "success": base_deployment_response_data["success"]
        }
        
        model_fixture = ModelTestFixture(DeploymentResponse, required_fields)
        response = model_fixture.create_instance(finished_at=base_deployment_response_data["finished_at"], 
                                                rollback_available=base_deployment_response_data["rollback_available"])
        
        assert model_fixture.validate_required_fields(response)
        assert response.status == "completed"
        assert response.success is True
        assert response.rollback_available is True
        
    def test_backup_response_model_shared(self, base_backup_response_data):
        """Тест модели ответа бэкапа из общих тестов."""
        from app.api.routes.backups import BackupResponse

        required_fields = {
            "id": base_backup_response_data["id"],
            "service_id": base_backup_response_data["service_id"],
            "name": base_backup_response_data["name"],
            "timestamp": base_backup_response_data["timestamp"],
            "status": base_backup_response_data["status"],
            "reason": base_backup_response_data["reason"]
        }
        
        model_fixture = ModelTestFixture(BackupResponse, required_fields)
        response = model_fixture.create_instance(size=base_backup_response_data["size"])
        
        assert model_fixture.validate_required_fields(response)
        assert response.name == "backup_20240101"
        assert response.status == "completed"
        
    def test_tls_validation_response_model_shared(self, base_tls_validation_response_data):
        """Тест модели ответа валидации TLS из общих тестов."""
        from app.api.routes.tls import TLSValidationResponse

        required_fields = {
            "status": base_tls_validation_response_data["status"],
            "domain": base_tls_validation_response_data["domain"]
        }
        
        model_fixture = ModelTestFixture(TLSValidationResponse, required_fields)
        response = model_fixture.create_instance(service=base_tls_validation_response_data["service"])
        
        assert model_fixture.validate_required_fields(response)
        assert response.status == "ok"
        assert response.domain == "test.example.com"
