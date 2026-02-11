"""Тесты для endpoints резервного копирования."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from datetime import datetime
from app.main import app

client = TestClient(app)


class TestBackupEndpoints:
    """Тесты для endpoints резервного копирования."""

    def test_list_service_backups_success(self):
        """Тест успешного получения списка бэкапов сервиса."""
        # Мокаем зависимости
        with patch('app.api.routes.backups.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.backups.app.state.discovery.get_service') as mock_get_service, \
             patch('app.api.routes.backups.app.state.backup.list_backups') as mock_list_backups:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сервис
            mock_service = Mock()
            mock_service.name = "testservice"
            mock_get_service.return_value = mock_service
            
            # Мокаем список бэкапов
            mock_backup_list = [
                {
                    "backup_name": "backup1",
                    "timestamp": "2023-01-01T10:00:00",
                    "reason": "manual"
                },
                {
                    "backup_name": "backup2",
                    "timestamp": "2023-01-02T10:00:00",
                    "reason": "scheduled"
                }
            ]
            mock_list_backups.return_value = mock_backup_list
            
            response = client.get("/api/backups/service/testservice")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["name"] == "backup1"
            assert data[1]["name"] == "backup2"

    def test_list_service_backups_with_pagination(self):
        """Тест получения списка бэкапов сервиса с пагинацией."""
        # Мокаем зависимости
        with patch('app.api.routes.backups.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.backups.app.state.discovery.get_service') as mock_get_service, \
             patch('app.api.routes.backups.app.state.backup.list_backups') as mock_list_backups:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сервис
            mock_service = Mock()
            mock_service.name = "testservice"
            mock_get_service.return_value = mock_service
            
            # Мокаем список бэкапов
            mock_backup_list = [
                {"backup_name": f"backup{i}", "timestamp": "2023-01-01T10:00:00", "reason": "manual"}
                for i in range(1, 11)  # 10 бэкапов
            ]
            mock_list_backups.return_value = mock_backup_list
            
            # Тест с пагинацией
            response = client.get("/api/backups/service/testservice", params={"skip": 5, "limit": 3})
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 3
            assert data[0]["name"] == "backup6"
            assert data[1]["name"] == "backup7"
            assert data[2]["name"] == "backup8"

    def test_list_service_backups_not_found(self):
        """Тест получения списка бэкапов несуществующего сервиса."""
        # Мокаем зависимости
        with patch('app.api.routes.backups.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.backups.app.state.discovery.get_service') as mock_get_service:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем отсутствие сервиса
            mock_get_service.return_value = None
            
            response = client.get("/api/backups/service/nonexistent")
            
            assert response.status_code == 404
            assert response.json()["detail"] == "Service not found"

    def test_create_backup_success(self):
        """Тест успешного создания бэкапа."""
        # Мокаем зависимости
        with patch('app.api.routes.backups.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.backups.app.state.discovery.get_service') as mock_get_service, \
             patch('app.api.routes.backups.app.state.backup.backup_service') as mock_backup_service:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сервис
            mock_service = Mock()
            mock_service.name = "testservice"
            mock_get_service.return_value = mock_service
            
            # Мокаем результат создания бэкапа
            mock_backup_result = {
                "success": True,
                "backup_name": "testservice_20230101_100000",
                "errors": []
            }
            mock_backup_service.return_value = mock_backup_result
            
            response = client.post("/api/backups/service/testservice/backup", json={
                "reason": "manual"
            })
            
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "testservice_20230101_100000"
            assert data["status"] == "completed"
            assert data["reason"] == "manual"
            mock_backup_service.assert_called_once_with(mock_service, reason="manual")

    def test_create_backup_failure(self):
        """Тест создания бэкапа с ошибкой."""
        # Мокаем зависимости
        with patch('app.api.routes.backups.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.backups.app.state.discovery.get_service') as mock_get_service, \
             patch('app.api.routes.backups.app.state.backup.backup_service') as mock_backup_service:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сервис
            mock_service = Mock()
            mock_service.name = "testservice"
            mock_get_service.return_value = mock_service
            
            # Мокаем результат создания бэкапа с ошибкой
            mock_backup_result = {
                "success": False,
                "errors": ["Backup failed due to disk space"]
            }
            mock_backup_service.return_value = mock_backup_result
            
            response = client.post("/api/backups/service/testservice/backup", json={
                "reason": "manual"
            })
            
            assert response.status_code == 500
            assert "Backup failed" in response.json()["detail"]

    def test_create_backup_not_found(self):
        """Тест создания бэкапа для несуществующего сервиса."""
        # Мокаем зависимости
        with patch('app.api.routes.backups.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.backups.app.state.discovery.get_service') as mock_get_service:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем отсутствие сервиса
            mock_get_service.return_value = None
            
            response = client.post("/api/backups/service/nonexistent/backup", json={
                "reason": "manual"
            })
            
            assert response.status_code == 404
            assert response.json()["detail"] == "Service not found"

    def test_restore_backup_success(self):
        """Тест успешного восстановления бэкапа."""
        # Мокаем зависимости
        with patch('app.api.routes.backups.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.backups.app.state.discovery.get_service') as mock_get_service:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем сервис
            mock_service = Mock()
            mock_service.name = "testservice"
            mock_get_service.return_value = mock_service
            
            response = client.post("/api/backups/service/testservice/restore", json={
                "backup_id": 123
            })
            
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Restore scheduled for service testservice"
            assert data["backup_id"] == 123

    def test_restore_backup_not_found(self):
        """Тест восстановления бэкапа для несуществующего сервиса."""
        # Мокаем зависимости
        with patch('app.api.routes.backups.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.backups.app.state.discovery.get_service') as mock_get_service:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            # Мокаем отсутствие сервиса
            mock_get_service.return_value = None
            
            response = client.post("/api/backups/service/nonexistent/restore", json={
                "backup_id": 123
            })
            
            assert response.status_code == 404
            assert response.json()["detail"] == "Service not found"

    def test_delete_backup_success(self):
        """Тест успешного удаления бэкапа."""
        # Мокаем зависимости
        with patch('app.api.routes.backups.get_current_user') as mock_get_current_user:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            response = client.delete("/api/backups/123")
            
            assert response.status_code == 200
            data = response.json()
            assert "scheduled for deletion" in data["message"]

    def test_get_backup_info_success(self):
        """Тест успешного получения информации о бэкапе."""
        # Мокаем зависимости
        with patch('app.api.routes.backups.get_current_user') as mock_get_current_user:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"username": "testuser"}
            
            response = client.get("/api/backups/123/info")
            
            assert response.status_code == 200
            data = response.json()
            assert data["backup_id"] == 123
            assert "Backup info" in data["message"]