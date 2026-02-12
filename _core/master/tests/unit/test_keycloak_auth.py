"""Тесты для KeycloakAuthProvider."""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from app.core.security import KeycloakAuthProvider


@pytest.fixture
def keycloak_auth_provider():
    """Фикстура для создания экземпляра KeycloakAuthProvider"""
    return KeycloakAuthProvider()


@pytest.mark.asyncio
async def test_keycloak_authenticate_success(keycloak_auth_provider):
    """Тест успешной аутентификации через Keycloak"""
    # Мокаем KeycloakOpenID
    with patch('app.core.security.KeycloakOpenID') as mock_keycloak:
        # Настраиваем мок для возврата токена и информации о пользователе
        mock_instance = Mock()
        mock_instance.token.return_value = {'access_token': 'test_token'}
        mock_instance.userinfo.return_value = {
            'sub': '1',
            'preferred_username': 'testuser',
            'email': 'testuser@example.com'
        }
        mock_keycloak.return_value = mock_instance
        
        # Устанавливаем мок в провайдер
        keycloak_auth_provider.keycloak_openid = mock_instance
        
        # Выполняем тест
        result = await keycloak_auth_provider.authenticate("testuser", "testpass")
        
        # Проверяем результат
        assert result is not None
        assert result['preferred_username'] == 'testuser'
        assert result['email'] == 'testuser@example.com'


@pytest.mark.asyncio
async def test_keycloak_authenticate_failure(keycloak_auth_provider):
    """Тест неудачной аутентификации через Keycloak"""
    # Мокаем KeycloakOpenID для выброса исключения
    with patch('app.core.security.KeycloakOpenID') as mock_keycloak:
        # Настраиваем мок для выброса исключения
        mock_instance = Mock()
        mock_instance.token.side_effect = Exception("Authentication failed")
        mock_keycloak.return_value = mock_instance
        
        # Устанавливаем мок в провайдер
        keycloak_auth_provider.keycloak_openid = mock_instance
        
        # Выполняем тест
        result = await keycloak_auth_provider.authenticate("testuser", "wrongpass")
        
        # Проверяем результат
        assert result is None


@pytest.mark.asyncio
async def test_keycloak_get_current_user_success(keycloak_auth_provider):
    """Тест успешного получения текущего пользователя через Keycloak"""
    # Мокаем KeycloakOpenID
    with patch('app.core.security.KeycloakOpenID') as mock_keycloak:
        # Настраиваем мок для возврата информации о пользователе
        mock_instance = Mock()
        mock_instance.userinfo.return_value = {
            'sub': '1',
            'preferred_username': 'testuser',
            'email': 'testuser@example.com'
        }
        mock_keycloak.return_value = mock_instance
        
        # Устанавливаем мок в провайдер
        keycloak_auth_provider.keycloak_openid = mock_instance
        
        # Выполняем тест
        result = await keycloak_auth_provider.get_current_user("test_token")
        
        # Проверяем результат
        assert result is not None
        assert result['preferred_username'] == 'testuser'
        assert result['email'] == 'testuser@example.com'


@pytest.mark.asyncio
async def test_keycloak_get_current_user_auth_error(keycloak_auth_provider):
    """Тест получения текущего пользователя с ошибкой аутентификации через Keycloak"""
    from keycloak.exceptions import KeycloakAuthenticationError
    
    # Мокаем KeycloakOpenID для выброса KeycloakAuthenticationError
    with patch('app.core.security.KeycloakOpenID') as mock_keycloak:
        # Настраиваем мок для выброса исключения
        mock_instance = Mock()
        mock_instance.userinfo.side_effect = KeycloakAuthenticationError("Token invalid")
        mock_keycloak.return_value = mock_instance
        
        # Устанавливаем мок в провайдер
        keycloak_auth_provider.keycloak_openid = mock_instance
        
        # Выполняем тест
        result = await keycloak_auth_provider.get_current_user("invalid_token")
        
        # Проверяем результат
        assert result is None


@pytest.mark.asyncio
async def test_keycloak_get_current_user_get_error(keycloak_auth_provider):
    """Тест получения текущего пользователя с ошибкой получения данных через Keycloak"""
    from keycloak.exceptions import KeycloakGetError
    
    # Мокаем KeycloakOpenID для выброса KeycloakGetError
    with patch('app.core.security.KeycloakOpenID') as mock_keycloak:
        # Настраиваем мок для выброса исключения
        mock_instance = Mock()
        mock_instance.userinfo.side_effect = KeycloakGetError("User not found")
        mock_keycloak.return_value = mock_instance
        
        # Устанавливаем мок в провайдер
        keycloak_auth_provider.keycloak_openid = mock_instance
        
        # Выполняем тест
        result = await keycloak_auth_provider.get_current_user("test_token")
        
        # Проверяем результат
        assert result is None


@pytest.mark.asyncio
async def test_keycloak_create_user(keycloak_auth_provider):
    """Тест создания пользователя через Keycloak (должен возвращать None)"""
    result = await keycloak_auth_provider.create_user("newuser", "newpass", ["user"])
    assert result is None