"""Тесты переключения провайдеров аутентификации."""
import pytest
from unittest.mock import patch, MagicMock
from app.core.security import (
    BuiltInAuthProvider,
    KeycloakAuthProvider,
    set_auth_provider,
)
import app.core.security as security_module


@pytest.fixture(autouse=True)
def reset_auth_provider():
    """Сброс auth_provider перед и после каждого теста."""
    security_module.auth_provider = None
    yield
    security_module.auth_provider = None


class TestAuthProviderSwitching:
    """Тесты переключения провайдеров."""

    def test_keycloak_provider_switching(self):
        """Тест переключения на Keycloak провайдер."""
        with patch("app.core.security.get_keycloak_client") as mock_get_client:
            mock_get_client.return_value = MagicMock()
            keycloak_provider = KeycloakAuthProvider()
            set_auth_provider(keycloak_provider)
            assert security_module.auth_provider == keycloak_provider

    def test_builtin_provider_switching(self):
        """Тест переключения на встроенный провайдер."""
        builtin_provider = BuiltInAuthProvider()
        set_auth_provider(builtin_provider)
        assert security_module.auth_provider == builtin_provider

    @pytest.mark.asyncio
    async def test_get_current_user_with_keycloak_provider(self):
        """Тест получения текущего пользователя с Keycloak провайдером."""
        with patch("app.core.security.get_keycloak_client") as mock_get_client:
            mock_keycloak = MagicMock()
            mock_keycloak.userinfo.return_value = {
                "sub": "1",
                "preferred_username": "testuser",
                "email": "testuser@example.com",
            }
            mock_get_client.return_value = mock_keycloak
            
            keycloak_provider = KeycloakAuthProvider()
            set_auth_provider(keycloak_provider)
            
            result = await keycloak_provider.get_current_user("test_token")
            
            assert result is not None
            assert result["preferred_username"] == "testuser"

    @pytest.mark.asyncio
    async def test_get_current_user_with_builtin_provider(self):
        """Тест получения текущего пользователя с builtin провайдером."""
        builtin_provider = BuiltInAuthProvider()
        set_auth_provider(builtin_provider)
        
        with patch("app.core.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db
            
            mock_user = MagicMock()
            mock_user.to_dict.return_value = {"id": 1, "username": "testuser"}
            mock_db.query.return_value.filter.return_value.first.return_value = mock_user
            
            result = await builtin_provider.get_current_user("1")
            
            assert result is not None
            assert result["username"] == "testuser"

    def test_get_current_user_with_no_provider(self):
        """Тест получения пользователя без провайдера."""
        from fastapi import HTTPException
        
        mock_credentials = MagicMock()
        mock_credentials.credentials = "test_token"
        
        import asyncio
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(security_module.get_current_user(mock_credentials))
        
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_get_current_user_with_invalid_token(self):
        """Тест получения пользователя с невалидным токеном."""
        builtin_provider = BuiltInAuthProvider()
        set_auth_provider(builtin_provider)
        
        result = await builtin_provider.get_current_user("invalid_token")
        assert result is None
