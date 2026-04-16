"""Тесты для Keycloak провайдера аутентификации."""
import pytest
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from app.core.security import KeycloakAuthProvider, get_keycloak_client


class TestKeycloakAuthProvider:
    """Тесты Keycloak провайдера аутентификации."""

    @pytest.fixture
    def mock_auth_provider(self):
        """Фикстура для создания Keycloak провайдера аутентификации."""
        # Создаем мок клиента и патчим метод получения клиента
        mock_client = MagicMock()
        with patch('app.core.security.get_keycloak_client', return_value=mock_client):
            provider = KeycloakAuthProvider()
            provider.keycloak = mock_client
            return provider, mock_client

    @pytest.mark.asyncio
    async def test_authenticate_success(self, mock_auth_provider):
        """Тест успешной аутентификации через Keycloak."""
        provider, mock_keycloak = mock_auth_provider
        
        mock_keycloak.token.return_value = {"access_token": "test_token"}
        mock_keycloak.userinfo.return_value = {
            "sub": "1", 
            "preferred_username": "testuser",
            "email": "testuser@example.com"
        }

        result = await provider.authenticate("testuser", "password")

        assert result is not None
        assert result["preferred_username"] == "testuser"
        assert result["email"] == "testuser@example.com"
        mock_keycloak.token.assert_called_once_with("testuser", "password")

    @pytest.mark.asyncio
    async def test_authenticate_failure(self, mock_auth_provider):
        """Тест неудачной аутентификации через Keycloak."""
        provider, mock_keycloak = mock_auth_provider
        
        mock_keycloak.token.side_effect = Exception("Invalid credentials")

        result = await provider.authenticate("testuser", "wrongpassword")

        assert result is None
        mock_keycloak.token.assert_called_once_with("testuser", "wrongpassword")

    @pytest.mark.asyncio
    async def test_get_current_user_success(self, mock_auth_provider):
        """Тест получения текущего пользователя через Keycloak."""
        provider, mock_keycloak = mock_auth_provider
        
        mock_keycloak.userinfo.return_value = {
            "sub": "1", 
            "preferred_username": "testuser",
            "email": "testuser@example.com"
        }

        result = await provider.get_current_user("valid_token")

        assert result is not None
        assert result["preferred_username"] == "testuser"
        assert result["email"] == "testuser@example.com"
        mock_keycloak.userinfo.assert_called_once_with("valid_token")

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, mock_auth_provider):
        """Тест получения пользователя с невалидным токеном."""
        provider, mock_keycloak = mock_auth_provider
        
        mock_keycloak.userinfo.side_effect = Exception("Invalid token")

        result = await provider.get_current_user("invalid_token")

        assert result is None
        mock_keycloak.userinfo.assert_called_once_with("invalid_token")

    @pytest.mark.asyncio
    async def test_create_user_unsupported(self, mock_auth_provider):
        """Тест создания пользователя через Keycloak (не поддерживается)."""
        provider, mock_keycloak = mock_auth_provider

        result = await provider.create_user("newuser", "password", ["role1"])

        assert result is None