"""Тесты для endpoints управления сервисами."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from app.main import app
from app.services.discovery import ServiceManifest

client = TestClient(app)


class TestServiceEndpoints:
    """Тесты для endpoints управления сервисами."""

    def test_list_services_success(self):
        """Тест успешного получения списка сервисов."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.main.app.state.discovery.services', new_callable=dict) as mock_services:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сервисы
            mock_service1 = Mock(spec=ServiceManifest)
            mock_service1.name = "service1"
            mock_service1.display_name = "Service 1"
            mock_service1.version = "1.0.0"
            mock_service1.status = "running"
            mock_service1.visibility = "public"
            mock_service1.type = "web"
            mock_service1.dict.return_value = {
                "name": "service1",
                "display_name": "Service 1",
                "version": "1.0.0",
                "status": "running",
                "visibility": "public",
                "type": "web"
            }
            
            mock_service2 = Mock(spec=ServiceManifest)
            mock_service2.name = "service2"
            mock_service2.display_name = "Service 2"
            mock_service2.version = "2.0.0"
            mock_service2.status = "stopped"
            mock_service2.visibility = "private"
            mock_service2.type = "api"
            mock_service2.dict.return_value = {
                "name": "service2",
                "display_name": "Service 2",
                "version": "2.0.0",
                "status": "stopped",
                "visibility": "private",
                "type": "api"
            }
            
            mock_services["service1"] = mock_service1
            mock_services["service2"] = mock_service2
            
            response = client.get("/api/services/")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["name"] == "service1"
            assert data[1]["name"] == "service2"

    def test_list_services_with_filters(self):
        """Тест получения списка сервисов с фильтрами."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.main.app.state.discovery.services', new_callable=dict) as mock_services:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сервисы
            mock_service1 = Mock(spec=ServiceManifest)
            mock_service1.name = "service1"
            mock_service1.display_name = "Service 1"
            mock_service1.version = "1.0.0"
            mock_service1.status = "running"
            mock_service1.visibility = "public"
            mock_service1.type = "web"
            mock_service1.dict.return_value = {
                "name": "service1",
                "display_name": "Service 1",
                "version": "1.0.0",
                "status": "running",
                "visibility": "public",
                "type": "web"
            }
            
            mock_service2 = Mock(spec=ServiceManifest)
            mock_service2.name = "service2"
            mock_service2.display_name = "Service 2"
            mock_service2.version = "2.0.0"
            mock_service2.status = "stopped"
            mock_service2.visibility = "private"
            mock_service2.type = "api"
            mock_service2.dict.return_value = {
                "name": "service2",
                "display_name": "Service 2",
                "version": "2.0.0",
                "status": "stopped",
                "visibility": "private",
                "type": "api"
            }
            
            mock_services["service1"] = mock_service1
            mock_services["service2"] = mock_service2
            
            # Тест фильтра по видимости
            response = client.get("/api/services/", params={"visibility": "public"})
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["name"] == "service1"
            
            # Тест фильтра по статусу
            response = client.get("/api/services/", params={"status": "stopped"})
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["name"] == "service2"

    def test_get_service_success(self):
        """Тест успешного получения деталей сервиса."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.main.app.state.discovery.get_service') as mock_get_service, \
             patch('app.main.app.state.docker.get_stats') as mock_get_stats:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сервис
            mock_service = Mock(spec=ServiceManifest)
            mock_service.name = "testservice"
            mock_service.display_name = "Test Service"
            mock_service.version = "1.0.0"
            mock_service.status = "running"
            mock_service.visibility = "public"
            mock_service.type = "web"
            mock_service.dict.return_value = {
                "name": "testservice",
                "display_name": "Test Service",
                "version": "1.0.0",
                "status": "running",
                "visibility": "public",
                "type": "web"
            }
            
            mock_get_service.return_value = mock_service
            
            # Мокаем статистику
            mock_stats = {"cpu": 10.5, "memory": 102400}
            mock_get_stats.return_value = mock_stats
            
            response = client.get("/api/services/testservice")
            
            assert response.status_code == 200
            data = response.json()
            assert data["manifest"]["name"] == "testservice"
            assert data["stats"] == mock_stats

    def test_get_service_not_found(self):
        """Тест получения деталей несуществующего сервиса."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.main.app.state.discovery.get_service') as mock_get_service:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем отсутствие сервиса
            mock_get_service.return_value = None
            
            response = client.get("/api/services/nonexistent")
            
            assert response.status_code == 404
            assert response.json()["detail"] == "Service not found"

    def test_deploy_service_success(self):
        """Тест успешного деплоя сервиса."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.main.app.state.discovery.get_service') as mock_get_service, \
             patch('app.main.app.state.docker.deploy_service') as mock_deploy_service, \
             patch('app.main.app.state.discovery.scan_all') as mock_scan_all, \
             patch('app.main.app.state.caddy.regenerate_all') as mock_regenerate_all:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сервис
            mock_service = Mock(spec=ServiceManifest)
            mock_service.name = "testservice"
            mock_get_service.return_value = mock_service
            
            # Мокаем результат деплоя
            mock_deploy_result = {"success": True, "message": "Deployed successfully"}
            mock_deploy_service.return_value = mock_deploy_result
            
            response = client.post("/api/services/testservice/deploy", json={
                "build": True,
                "pull": False
            })
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["message"] == "Deployed successfully"
            mock_deploy_service.assert_called_once_with(mock_service, build=True, pull=False)
            mock_scan_all.assert_called_once()
            mock_regenerate_all.assert_called_once()

    def test_deploy_service_not_found(self):
        """Тест деплоя несуществующего сервиса."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.main.app.state.discovery.get_service') as mock_get_service:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем отсутствие сервиса
            mock_get_service.return_value = None
            
            response = client.post("/api/services/nonexistent/deploy", json={
                "build": True,
                "pull": False
            })
            
            assert response.status_code == 404
            assert response.json()["detail"] == "Service not found"

    def test_stop_service_success(self):
        """Тест успешной остановки сервиса."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.main.app.state.discovery.get_service') as mock_get_service, \
             patch('app.main.app.state.docker.stop_service') as mock_stop_service:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сервис
            mock_service = Mock(spec=ServiceManifest)
            mock_service.name = "testservice"
            mock_get_service.return_value = mock_service
            
            # Мокаем результат остановки
            mock_stop_result = {"success": True, "message": "Stopped successfully"}
            mock_stop_service.return_value = mock_stop_result
            
            response = client.post("/api/services/testservice/stop")
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["message"] == "Stopped successfully"
            mock_stop_service.assert_called_once_with(mock_service)

    def test_stop_service_not_found(self):
        """Тест остановки несуществующего сервиса."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.main.app.state.discovery.get_service') as mock_get_service:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем отсутствие сервиса
            mock_get_service.return_value = None
            
            response = client.post("/api/services/nonexistent/stop")
            
            assert response.status_code == 404
            assert response.json()["detail"] == "Service not found"

    def test_restart_service_success(self):
        """Тест успешного перезапуска сервиса."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.main.app.state.discovery.get_service') as mock_get_service, \
             patch('app.main.app.state.docker.restart_service') as mock_restart_service:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сервис
            mock_service = Mock(spec=ServiceManifest)
            mock_service.name = "testservice"
            mock_get_service.return_value = mock_service
            
            # Мокаем результат перезапуска
            mock_restart_result = {"success": True, "message": "Restarted successfully"}
            mock_restart_service.return_value = mock_restart_result
            
            response = client.post("/api/services/testservice/restart")
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["message"] == "Restarted successfully"
            mock_restart_service.assert_called_once_with(mock_service)

    def test_restart_service_not_found(self):
        """Тест перезапуска несуществующего сервиса."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.main.app.state.discovery.get_service') as mock_get_service:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем отсутствие сервиса
            mock_get_service.return_value = None
            
            response = client.post("/api/services/nonexistent/restart")
            
            assert response.status_code == 404
            assert response.json()["detail"] == "Service not found"