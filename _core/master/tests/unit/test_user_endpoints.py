"""Тесты для endpoints управления пользователями."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from app.main import app
from app.models.user import User

client = TestClient(app)


class TestUserEndpoints:
    """Тесты для endpoints управления пользователями."""

    def test_list_users_success(self):
        """Тест успешного получения списка пользователей."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.users.get_db') as mock_get_db:
            
            # Мокаем текущего пользователя (суперпользователя)
            mock_get_current_user.return_value = {"is_superuser": True}
            
            # Мокаем сессию базы данных
            mock_db = Mock()
            mock_user1 = User(id=1, username="user1", email="user1@example.com", is_superuser=False)
            mock_user2 = User(id=2, username="user2", email="user2@example.com", is_superuser=True)
            mock_db.query().all.return_value = [mock_user1, mock_user2]
            mock_get_db.return_value = mock_db
            
            response = client.get("/api/users/")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["username"] == "user1"
            assert data[1]["username"] == "user2"

    def test_list_users_forbidden(self):
        """Тест получения списка пользователей без прав доступа."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user:
            # Мокаем текущего пользователя (обычного пользователя)
            mock_get_current_user.return_value = {"is_superuser": False}
            
            response = client.get("/api/users/")
            
            assert response.status_code == 403
            assert response.json()["detail"] == "Not enough permissions"

    def test_create_user_success(self):
        """Тест успешного создания пользователя."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.users.get_db') as mock_get_db, \
             patch('app.api.routes.users.auth_provider') as mock_auth_provider:
            
            # Мокаем текущего пользователя (суперпользователя)
            mock_get_current_user.return_value = {"is_superuser": True}
            
            # Мокаем сессию базы данных
            mock_db = Mock()
            mock_db.query().filter().first.return_value = None  # Пользователь не существует
            mock_get_db.return_value = mock_db
            
            # Мокаем провайдер аутентификации
            mock_auth_provider.create_user.return_value = {
                "id": 1,
                "username": "newuser",
                "email": "newuser@example.com"
            }
            
            response = client.post("/api/users/", data={
                "username": "newuser",
                "password": "newpass",
                "email": "newuser@example.com",
                "is_superuser": False
            })
            
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "User created successfully"
            assert data["user"]["username"] == "newuser"

    def test_create_user_already_exists(self):
        """Тест создания пользователя, который уже существует."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.users.get_db') as mock_get_db:
            
            # Мокаем текущего пользователя (суперпользователя)
            mock_get_current_user.return_value = {"is_superuser": True}
            
            # Мокаем сессию базы данных
            mock_db = Mock()
            mock_existing_user = User(id=1, username="existinguser", email="existing@example.com")
            mock_db.query().filter().first.return_value = mock_existing_user
            mock_get_db.return_value = mock_db
            
            response = client.post("/api/users/", data={
                "username": "existinguser",
                "password": "newpass",
                "email": "newuser@example.com"
            })
            
            assert response.status_code == 400
            assert response.json()["detail"] == "User already exists"

    def test_create_user_forbidden(self):
        """Тест создания пользователя без прав доступа."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user:
            # Мокаем текущего пользователя (обычного пользователя)
            mock_get_current_user.return_value = {"is_superuser": False}
            
            response = client.post("/api/users/", data={
                "username": "newuser",
                "password": "newpass",
                "email": "newuser@example.com"
            })
            
            assert response.status_code == 403
            assert response.json()["detail"] == "Not enough permissions"

    def test_get_user_success(self):
        """Тест успешного получения информации о пользователе."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.users.get_db') as mock_get_db:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"is_superuser": True, "sub": "1"}
            
            # Мокаем сессию базы данных
            mock_db = Mock()
            mock_user = User(id=1, username="testuser", email="test@example.com", is_superuser=False)
            mock_db.query().filter().first.return_value = mock_user
            mock_get_db.return_value = mock_db
            
            response = client.get("/api/users/1")
            
            assert response.status_code == 200
            data = response.json()
            assert data["username"] == "testuser"
            assert data["email"] == "test@example.com"

    def test_get_user_not_found(self):
        """Тест получения информации о несуществующем пользователе."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.users.get_db') as mock_get_db:
            
            # Мокаем текущего пользователя
            mock_get_current_user.return_value = {"is_superuser": True, "sub": "1"}
            
            # Мокаем сессию базы данных
            mock_db = Mock()
            mock_db.query().filter().first.return_value = None  # Пользователь не найден
            mock_get_db.return_value = mock_db
            
            response = client.get("/api/users/999")
            
            assert response.status_code == 404
            assert response.json()["detail"] == "User not found"

    def test_update_user_success(self):
        """Тест успешного обновления информации о пользователе."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.users.get_db') as mock_get_db:
            
            # Мокаем текущего пользователя (суперпользователя)
            mock_get_current_user.return_value = {"is_superuser": True, "sub": "1"}
            
            # Мокаем сессию базы данных
            mock_db = Mock()
            mock_user = User(id=1, username="olduser", email="old@example.com", is_active=True, is_superuser=False)
            mock_db.query().filter().first.return_value = mock_user
            mock_get_db.return_value = mock_db
            
            response = client.put("/api/users/1", json={
                "username": "updateduser",
                "email": "updated@example.com",
                "is_active": False,
                "is_superuser": True
            })
            
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "User updated successfully"
            assert mock_user.username == "updateduser"
            assert mock_user.email == "updated@example.com"
            assert mock_user.is_active is False
            assert mock_user.is_superuser is True

    def test_update_user_forbidden(self):
        """Тест обновления информации о пользователе без прав доступа."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user:
            # Мокаем текущего пользователя (обычного пользователя, не владелец)
            mock_get_current_user.return_value = {"is_superuser": False, "sub": "2"}
            
            response = client.put("/api/users/1", json={
                "username": "updateduser"
            })
            
            assert response.status_code == 403
            assert response.json()["detail"] == "Not enough permissions"

    def test_delete_user_success(self):
        """Тест успешного удаления пользователя."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.users.get_db') as mock_get_db:
            
            # Мокаем текущего пользователя (суперпользователя)
            mock_get_current_user.return_value = {"is_superuser": True}
            
            # Мокаем сессию базы данных
            mock_db = Mock()
            mock_user = User(id=1, username="user_to_delete")
            mock_db.query().filter().first.return_value = mock_user
            mock_get_db.return_value = mock_db
            
            response = client.delete("/api/users/1")
            
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "User deleted successfully"
            mock_db.delete.assert_called_once_with(mock_user)

    def test_delete_user_forbidden(self):
        """Тест удаления пользователя без прав доступа."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user:
            # Мокаем текущего пользователя (обычного пользователя)
            mock_get_current_user.return_value = {"is_superuser": False}
            
            response = client.delete("/api/users/1")
            
            assert response.status_code == 403
            assert response.json()["detail"] == "Not enough permissions"

    def test_delete_user_not_found(self):
        """Тест удаления несуществующего пользователя."""
        # Мокаем зависимости
        with patch('app.core.security.get_current_user') as mock_get_current_user, \
             patch('app.api.routes.users.get_db') as mock_get_db:
            
            # Мокаем текущего пользователя (суперпользователя)
            mock_get_current_user.return_value = {"is_superuser": True}
            
            # Мокаем сессию базы данных
            mock_db = Mock()
            mock_db.query().filter().first.return_value = None  # Пользователь не найден
            mock_get_db.return_value = mock_db
            
            response = client.delete("/api/users/999")
            
            assert response.status_code == 404
            assert response.json()["detail"] == "User not found"