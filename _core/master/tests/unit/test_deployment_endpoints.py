"""Тесты для моделей - общие проверки дублирующихся Pydantic-моделей."""
import pytest
from datetime import datetime, timezone

from .test_model_utils import ModelTestFixture


class TestSharedDeploymentModels:
    """Тесты Pydantic моделей для деплоев, перемещенные и объединенные из других файлов."""

    def test_deployment_log_response(self, sample_datetime):
        """Тест модели DeploymentLogResponse."""
        from app.api.routes.deployments import DeploymentLogResponse

        required_fields = {
            "id": 1,
            "deployment_id": 1,
            "level": "info",
            "message": "Deployment started",
            "timestamp": sample_datetime
        }

        model_fixture = ModelTestFixture(DeploymentLogResponse, required_fields)
        response = model_fixture.create_instance()

        assert model_fixture.validate_required_fields(response)
        assert response.level == "info"
        assert response.message == "Deployment started"

    def test_deploy_request(self):
        """Тест модели DeployRequest."""
        from app.api.routes.deployments import DeployRequest

        request = DeployRequest(version="2.0.0", build=True, pull=False)
        assert request.version == "2.0.0"
        assert request.build is True
        assert request.pull is False

    def test_deploy_request_defaults(self):
        """Тест дефолтных значений DeployRequest."""
        from app.api.routes.deployments import DeployRequest

        request = DeployRequest(version="1.0.0")
        assert request.build is True
        assert request.pull is False
