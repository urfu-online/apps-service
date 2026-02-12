"""Тесты для endpoints аутентификации."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from app.main import app

client = TestClient(app)


class TestAuthEndpoints:
    """Тесты для endpoints аутентификации."""

    def test_login_success(self):
        """Тест успешной аутентификации."""
        # Мокаем провайдер аутентификации
        with patch('app.core.security.get_auth_provider') as mock_provider:
            mock_auth_provider = Mock()
            mock_auth_provider.authenticate.return_value = {
                "access_token": "test_token",
                "token_type": "bearer"
            }
            mock_provider.return_value = mock_auth_provider
            
            response = client.post(
                "/api/auth/login",
                data={
                    "username": "testuser",
                    "password": "testpass"
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"
            mock_auth_provider.authenticate.assert_called_once_with("testuser", "testpass")

    def test_login_invalid_credentials(self):
        """Тест аутентификации с неверными учетными данными."""
        # Мокаем провайдер аутентификации
        with patch('app.core.security.get_auth_provider') as mock_provider:
            mock_auth_provider = Mock()
            mock_auth_provider.authenticate.return_value = None
            mock_provider.return_value = mock_auth_provider
            
            response = client.post(
                "/api/auth/login",
                data={
                    "username": "invaliduser",
                    "password": "invalidpass"
                }
            )
            
            assert response.status_code == 401
            assert response.json()["detail"] == "Invalid credentials"

    def test_login_missing_credentials(self):
        """Тест аутентификации с отсутствующими учетными данными."""
        response = client.post("/api/auth/login", data={})
        
        assert response.status_code == 422  # Unprocessable Entity

    def test_logout(self):
        """Тест выхода из системы."""
        # Мокаем провайдер аутентификации
        with patch('app.core.security.get_auth_provider') as mock_provider:
            mock_auth_provider = Mock()
            mock_provider.return_value = mock_auth_provider
            
            response = client.post("/api/auth/logout")
            
            assert response.status_code == 200
            assert response.json()["message"] == "Successfully logged out"

    def test_get_current_user(self):
        """Тест получения информации о текущем пользователе."""
        # Мокаем провайдер аутентификации
        with patch('app.core.security.get_auth_provider') as mock_provider:
            mock_auth_provider = Mock()
            mock_auth_provider.get_user_info.return_value = {
                "sub": "123",
                "username": "testuser",
                "is_superuser": True
            }
            mock_provider.return_value = mock_auth_provider
            
            # Создаем заголовок авторизации
            headers = {"Authorization": "Bearer test_token"}
            
            response = client.get("/api/auth/me", headers=headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["username"] == "testuser"
            assert data["is_superuser"] is True