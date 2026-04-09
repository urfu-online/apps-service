"""Тесты для endpoints логов."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from app.main import app

client = TestClient(app)


class TestLogEndpoints:
    """Тесты для endpoints логов."""

    def test_get_service_logs_success(self):
        """Тест успешного получения логов сервиса."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.main.app.state.discovery.get_service') as mock_get_service, \
             patch('app.main.app.state.docker.get_logs') as mock_get_logs:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сервис
            mock_service = Mock()
            mock_service.name = "testservice"
            mock_get_service.return_value = mock_service
            
            # Мокаем логи
            mock_logs = "line1\nline2\nline3"
            mock_get_logs.return_value = mock_logs
            
            response = client.get("/api/logs/service/testservice", params={"tail": 50})
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 3
            assert data[0] == "line1"
            assert data[1] == "line2"
            assert data[2] == "line3"
            mock_get_logs.assert_called_once_with(mock_service, tail=50, since=None)

    def test_get_service_logs_with_since(self):
        """Тест получения логов сервиса с параметром since."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.main.app.state.discovery.get_service') as mock_get_service, \
             patch('app.main.app.state.docker.get_logs') as mock_get_logs:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сервис
            mock_service = Mock()
            mock_service.name = "testservice"
            mock_get_service.return_value = mock_service
            
            # Мокаем логи
            mock_logs = "line1\nline2"
            mock_get_logs.return_value = mock_logs
            
            response = client.get("/api/logs/service/testservice", params={
                "tail": 100,
                "since": "2023-01-01T10:00:00"
            })
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            mock_get_logs.assert_called_once_with(mock_service, tail=100, since="2023-01-01T10:00:00")

    def test_get_service_logs_not_found(self):
        """Тест получения логов несуществующего сервиса."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.main.app.state.discovery.get_service') as mock_get_service:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем отсутствие сервиса
            mock_get_service.return_value = None
            
            response = client.get("/api/logs/service/nonexistent")
            
            assert response.status_code == 404
            assert response.json()["detail"] == "Service not found"

    def test_search_service_logs_success(self):
        """Тест успешного поиска по логам сервиса."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.main.app.state.discovery.get_service') as mock_get_service, \
             patch('app.main.app.state.log_manager.get_service_logs') as mock_get_service_logs:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сервис
            mock_service = Mock()
            mock_service.name = "testservice"
            mock_get_service.return_value = mock_service
            
            # Мокаем логи сервиса
            mock_service_logs = [
                "2023-01-01 10:00:00 INFO Starting service",
                "2023-01-01 10:00:01 ERROR Connection failed",
                "2023-01-01 10:00:02 INFO Service started",
                "2023-01-01 10:00:03 ERROR Database connection lost"
            ]
            mock_get_service_logs.return_value = mock_service_logs
            
            response = client.post("/api/logs/service/testservice/search", json={
                "query": "ERROR",
                "limit": 10
            })
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert "ERROR Connection failed" in data[0]
            assert "ERROR Database connection lost" in data[1]

    def test_search_service_logs_with_limit(self):
        """Тест поиска по логам сервиса с ограничением количества результатов."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.main.app.state.discovery.get_service') as mock_get_service, \
             patch('app.main.app.state.log_manager.get_service_logs') as mock_get_service_logs:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сервис
            mock_service = Mock()
            mock_service.name = "testservice"
            mock_get_service.return_value = mock_service
            
            # Мокаем логи сервиса
            mock_service_logs = [
                f"2023-01-01 10:00:{i:02d} ERROR Error message {i}"
                for i in range(1, 11)  # 10 ошибок
            ]
            mock_get_service_logs.return_value = mock_service_logs
            
            response = client.post("/api/logs/service/testservice/search", json={
                "query": "ERROR",
                "limit": 5
            })
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 5
            # Проверяем, что возвращены последние 5 совпадений
            assert "Error message 6" in data[0]
            assert "Error message 10" in data[4]

    def test_search_service_logs_not_found(self):
        """Тест поиска по логам несуществующего сервиса."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.main.app.state.discovery.get_service') as mock_get_service:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем отсутствие сервиса
            mock_get_service.return_value = None
            
            response = client.post("/api/logs/service/nonexistent/search", json={
                "query": "ERROR"
            })
            
            assert response.status_code == 404
            assert response.json()["detail"] == "Service not found"

    def test_get_log_stats_success(self):
        """Тест успешного получения статистики по логам сервиса."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.main.app.state.discovery.get_service') as mock_get_service, \
             patch('app.main.app.state.log_manager.get_log_stats') as mock_get_log_stats:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сервис
            mock_service = Mock()
            mock_service.name = "testservice"
            mock_get_service.return_value = mock_service
            
            # Мокаем статистику логов
            mock_stats = {
                "total_lines": 1000,
                "error_count": 10,
                "warning_count": 20,
                "last_updated": "2023-01-01T10:00:00"
            }
            mock_get_log_stats.return_value = mock_stats
            
            response = client.get("/api/logs/service/testservice/stats")
            
            assert response.status_code == 200
            data = response.json()
            assert data["total_lines"] == 1000
            assert data["error_count"] == 10
            assert data["warning_count"] == 20

    def test_get_log_stats_not_found(self):
        """Тест получения статистики по логам несуществующего сервиса."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.main.app.state.discovery.get_service') as mock_get_service:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем отсутствие сервиса
            mock_get_service.return_value = None
            
            response = client.get("/api/logs/service/nonexistent/stats")
            
            assert response.status_code == 404
            assert response.json()["detail"] == "Service not found"

    def test_export_service_logs_success(self):
        """Тест успешного экспорта логов сервиса."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.main.app.state.discovery.get_service') as mock_get_service:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сервис
            mock_service = Mock()
            mock_service.name = "testservice"
            mock_get_service.return_value = mock_service
            
            response = client.get("/api/logs/service/testservice/export")
            
            assert response.status_code == 200
            data = response.json()
            assert "scheduled for" in data["message"]
            assert data["filename"].startswith("testservice_logs_")
            assert data["filename"].endswith(".txt")

    def test_export_service_logs_not_found(self):
        """Тест экспорта логов несуществующего сервиса."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.main.app.state.discovery.get_service') as mock_get_service:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем отсутствие сервиса
            mock_get_service.return_value = None
            
            response = client.get("/api/logs/service/nonexistent/export")
            
            assert response.status_code == 404
            assert response.json()["detail"] == "Service not found"