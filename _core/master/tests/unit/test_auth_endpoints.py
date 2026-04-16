"""Тесты для аутентификации через auth providers."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from app.core.security import BuiltInAuthProvider, KeycloakAuthProvider


class TestBuiltInAuthProvider:
    """Тесты встроенного провайдера аутентификации."""

    @pytest.mark.asyncio
    async def test_authenticate_success(self):
        """Тест успешной аутентификации."""
        provider = BuiltInAuthProvider()
        
        with patch("app.core.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db
            
            mock_user = MagicMock()
            mock_user.check_password.return_value = True
            mock_user.to_dict.return_value = {"id": 1, "username": "testuser"}
            mock_db.query.return_value.filter.return_value.first.return_value = mock_user
            
            result = await provider.authenticate("testuser", "password")
            
            assert result is not None
            assert result["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(self):
        """Тест аутентификации с несуществующим пользователем."""
        provider = BuiltInAuthProvider()
        
        with patch("app.core.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = None
            
            result = await provider.authenticate("nonexistent", "password")
            assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_wrong_password(self):
        """Тест аутентификации с неверным паролем."""
        provider = BuiltInAuthProvider()
        
        with patch("app.core.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db
            
            mock_user = MagicMock()
            mock_user.check_password.return_value = False
            mock_db.query.return_value.filter.return_value.first.return_value = mock_user
            
            result = await provider.authenticate("testuser", "wrongpassword")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_current_user_success(self):
        """Тест получения текущего пользователя по токену."""
        provider = BuiltInAuthProvider()
        
        with patch("app.core.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db
            
            mock_user = MagicMock()
            mock_user.to_dict.return_value = {"id": 1, "username": "testuser"}
            mock_db.query.return_value.filter.return_value.first.return_value = mock_user
            
            result = await provider.get_current_user("1")
            
            assert result is not None
            assert result["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self):
        """Тест получения пользователя с невалидным токеном."""
        provider = BuiltInAuthProvider()
        
        result = await provider.get_current_user("invalid_token")
        assert result is None

    @pytest.mark.asyncio
    async def test_create_user_success(self):
        """Тест создания пользователя."""
        provider = BuiltInAuthProvider()
        
        with patch("app.core.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.side_effect = [None, MagicMock()]
            
            mock_user = MagicMock()
            mock_user.to_dict.return_value = {"id": 1, "username": "newuser"}
            
            with patch("app.models.user.User") as MockUser:
                MockUser.return_value = mock_user
                result = await provider.create_user("newuser", "password", [])
                
            assert result is not None
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_user_already_exists(self):
        """Тест создания уже существующего пользователя."""
        provider = BuiltInAuthProvider()
        
        with patch("app.core.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db
            
            mock_existing = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = mock_existing
            
            result = await provider.create_user("existinguser", "password", [])
            assert result is None


class TestKeycloakAuthProvider:
    """Тесты Keycloak провайдера аутентификации."""

    @pytest.mark.asyncio
    async def test_authenticate_success(self):
        """Тест успешной аутентификации через Keycloak."""
        with patch("app.core.security.get_keycloak_client") as mock_get_client:
            mock_keycloak = MagicMock()
            mock_keycloak.token.return_value = {"access_token": "test_token"}
            mock_keycloak.userinfo.return_value = {"sub": "1", "preferred_username": "testuser"}
            mock_get_client.return_value = mock_keycloak
            
            provider = KeycloakAuthProvider()
            result = await provider.authenticate("testuser", "password")
            
            assert result is not None
            assert result["preferred_username"] == "testuser"

    @pytest.mark.asyncio
    async def test_get_current_user_success(self):
        """Тест получения текущего пользователя через Keycloak."""
        with patch("app.core.security.get_keycloak_client") as mock_get_client:
            mock_keycloak = MagicMock()
            mock_keycloak.userinfo.return_value = {"sub": "1", "preferred_username": "testuser"}
            mock_get_client.return_value = mock_keycloak
            
            provider = KeycloakAuthProvider()
            result = await provider.get_current_user("test_token")
            
            assert result is not None
            assert result["preferred_username"] == "testuser"


class TestAuthProviderSwitching:
    """Тесты переключения провайдеров аутентификации."""

    def test_set_auth_provider(self):
        """Тест установки провайдера аутентификации."""
        from app.core.security import set_auth_provider
        import app.core.security as security_module
        
        provider = BuiltInAuthProvider()
        set_auth_provider(provider)
        
        assert security_module.auth_provider == provider
        
        # Сброс
        security_module.auth_provider = None
