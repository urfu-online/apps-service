"""Тесты для endpoints развертывания."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from datetime import datetime
from app.main import app
from app.models.deployment import Deployment, DeploymentLog

client = TestClient(app)


class TestDeploymentEndpoints:
    """Тесты для endpoints развертывания."""

    def test_list_deployments_success(self):
        """Тест успешного получения списка деплоев."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.deployments.get_db') as mock_get_db:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сессию базы данных
            mock_db = Mock()
            mock_deployment1 = Deployment(
                id=1,
                service_id=1,
                version="1.0.0",
                status="completed",
                started_at=datetime(2023, 1, 1, 10, 0, 0),
                finished_at=datetime(2023, 1, 1, 10, 5, 0),
                success=True,
                rollback_available=True
            )
            mock_deployment2 = Deployment(
                id=2,
                service_id=1,
                version="1.1.0",
                status="failed",
                started_at=datetime(2023, 1, 2, 10, 0, 0),
                finished_at=datetime(2023, 1, 2, 10, 3, 0),
                success=False,
                rollback_available=False
            )
            
            mock_query = Mock()
            mock_query.filter().order_by().offset().limit().all.return_value = [mock_deployment1, mock_deployment2]
            mock_db.query.return_value = mock_query
            mock_get_db.return_value = mock_db
            
            response = client.get("/api/deployments/service/1")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["id"] == 1
            assert data[0]["version"] == "1.0.0"
            assert data[1]["id"] == 2
            assert data[1]["version"] == "1.1.0"

    def test_list_deployments_with_pagination(self):
        """Тест получения списка деплоев с пагинацией."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.deployments.get_db') as mock_get_db:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сессию базы данных
            mock_db = Mock()
            mock_deployments = [
                Deployment(
                    id=i,
                    service_id=1,
                    version=f"1.0.{i}",
                    status="completed",
                    started_at=datetime(2023, 1, 1, 10, i, 0),
                    finished_at=datetime(2023, 1, 1, 10, i+1, 0),
                    success=True,
                    rollback_available=True
                )
                for i in range(1, 11)  # 10 деплоев
            ]
            
            mock_query = Mock()
            mock_query.filter().order_by().offset().limit().all.return_value = mock_deployments[5:8]  # skip=5, limit=3
            mock_db.query.return_value = mock_query
            mock_get_db.return_value = mock_db
            
            response = client.get("/api/deployments/service/1", params={"skip": 5, "limit": 3})
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 3
            assert data[0]["id"] == 6
            assert data[1]["id"] == 7
            assert data[2]["id"] == 8

    def test_get_deployment_success(self):
        """Тест успешного получения информации о деплое."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.deployments.get_db') as mock_get_db:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сессию базы данных
            mock_db = Mock()
            mock_deployment = Deployment(
                id=1,
                service_id=1,
                version="1.0.0",
                status="completed",
                started_at=datetime(2023, 1, 1, 10, 0, 0),
                finished_at=datetime(2023, 1, 1, 10, 5, 0),
                success=True,
                rollback_available=True
            )
            
            mock_db.query().filter().first.return_value = mock_deployment
            mock_get_db.return_value = mock_db
            
            response = client.get("/api/deployments/1")
            
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == 1
            assert data["version"] == "1.0.0"
            assert data["status"] == "completed"

    def test_get_deployment_not_found(self):
        """Тест получения информации о несуществующем деплое."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.deployments.get_db') as mock_get_db:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сессию базы данных
            mock_db = Mock()
            mock_db.query().filter().first.return_value = None
            mock_get_db.return_value = mock_db
            
            response = client.get("/api/deployments/999")
            
            assert response.status_code == 404
            assert response.json()["detail"] == "Deployment not found"

    def test_get_deployment_logs_success(self):
        """Тест успешного получения логов деплоя."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.deployments.get_db') as mock_get_db:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сессию базы данных
            mock_db = Mock()
            mock_log1 = DeploymentLog(
                id=1,
                deployment_id=1,
                level="info",
                message="Deployment started",
                timestamp=datetime(2023, 1, 1, 10, 0, 0)
            )
            mock_log2 = DeploymentLog(
                id=2,
                deployment_id=1,
                level="error",
                message="Connection failed",
                timestamp=datetime(2023, 1, 1, 10, 1, 0)
            )
            
            mock_query = Mock()
            mock_query.filter().order_by().offset().limit().all.return_value = [mock_log1, mock_log2]
            mock_db.query.return_value = mock_query
            mock_get_db.return_value = mock_db
            
            response = client.get("/api/deployments/1/logs")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["message"] == "Deployment started"
            assert data[1]["message"] == "Connection failed"

    def test_get_deployment_logs_with_filter(self):
        """Тест получения логов деплоя с фильтрацией по уровню."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.deployments.get_db') as mock_get_db:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сессию базы данных
            mock_db = Mock()
            mock_error_log = DeploymentLog(
                id=2,
                deployment_id=1,
                level="error",
                message="Connection failed",
                timestamp=datetime(2023, 1, 1, 10, 1, 0)
            )
            
            mock_query = Mock()
            mock_filtered_query = Mock()
            mock_query.filter().filter.return_value = mock_filtered_query
            mock_filtered_query.order_by().offset().limit().all.return_value = [mock_error_log]
            mock_db.query.return_value = mock_query
            mock_get_db.return_value = mock_db
            
            response = client.get("/api/deployments/1/logs", params={"level": "error"})
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["level"] == "error"
            assert data[0]["message"] == "Connection failed"

    def test_start_deployment_success(self):
        """Тест успешного запуска деплоя."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.deployments.get_db') as mock_get_db, \
             patch('app.main.app.state.discovery.services', new_callable=dict) as mock_services, \
             patch('app.api.routes.deployments.asyncio.create_task') as mock_create_task:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сессию базы данных
            mock_db = Mock()
            mock_deployment = Deployment(
                id=1,
                service_id=1,
                version="1.0.0",
                status="pending"
            )
            mock_db.add = Mock()
            mock_db.commit = Mock()
            mock_db.refresh = Mock()
            mock_get_db.return_value = mock_db
            
            # Мокаем сервис
            mock_service = Mock()
            mock_service.id = 1
            mock_service.name = "testservice"
            mock_services[1] = mock_service
            
            response = client.post("/api/deployments/service/1/deploy", json={
                "version": "1.0.0",
                "build": True,
                "pull": False
            })
            
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == 1
            assert data["version"] == "1.0.0"
            assert data["status"] == "pending"
            mock_create_task.assert_called_once()

    def test_start_deployment_service_not_found(self):
        """Тест запуска деплоя для несуществующего сервиса."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.deployments.get_db') as mock_get_db, \
             patch('app.main.app.state.discovery.services', new_callable=dict) as mock_services:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сессию базы данных
            mock_get_db.return_value = Mock()
            
            # Мокаем отсутствие сервисов
            mock_services.clear()
            
            response = client.post("/api/deployments/service/999/deploy", json={
                "version": "1.0.0"
            })
            
            assert response.status_code == 404
            assert response.json()["detail"] == "Service not found"

    def test_rollback_deployment_success(self):
        """Тест успешного отката деплоя."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.deployments.get_db') as mock_get_db, \
             patch('app.api.routes.deployments.asyncio.create_task') as mock_create_task:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сессию базы данных
            mock_db = Mock()
            mock_deployment = Deployment(
                id=1,
                service_id=1,
                version="1.0.0",
                status="completed",
                rollback_available=True
            )
            mock_db.query().filter().first.return_value = mock_deployment
            mock_db.commit = Mock()
            mock_get_db.return_value = mock_db
            
            response = client.post("/api/deployments/1/rollback")
            
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == 1
            assert data["status"] == "rolling_back"
            mock_create_task.assert_called_once()

    def test_rollback_deployment_not_found(self):
        """Тест отката несуществующего деплоя."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.deployments.get_db') as mock_get_db:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сессию базы данных
            mock_db = Mock()
            mock_db.query().filter().first.return_value = None
            mock_get_db.return_value = mock_db
            
            response = client.post("/api/deployments/999/rollback")
            
            assert response.status_code == 404
            assert response.json()["detail"] == "Deployment not found"

    def test_rollback_deployment_not_available(self):
        """Тест отката деплоя, когда откат недоступен."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.deployments.get_db') as mock_get_db:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сессию базы данных
            mock_db = Mock()
            mock_deployment = Deployment(
                id=1,
                service_id=1,
                version="1.0.0",
                status="completed",
                rollback_available=False
            )
            mock_db.query().filter().first.return_value = mock_deployment
            mock_get_db.return_value = mock_db
            
            response = client.post("/api/deployments/1/rollback")
            
            assert response.status_code == 400
            assert response.json()["detail"] == "Rollback not available for this deployment"