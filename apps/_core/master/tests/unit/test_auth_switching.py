"""Тесты для переключения между провайдерами аутентификации."""
import pytest
from unittest.mock import Mock, patch
from app.core.security import KeycloakAuthProvider, BuiltInAuthProvider, set_auth_provider, auth_provider, get_current_user
from app.config import settings
from fastapi import HTTPException


@pytest.fixture
def mock_credentials():
    """Фикстура для создания мок-учетных данных"""
    credentials = Mock()
    credentials.credentials = "test_token"
    return credentials


@pytest.mark.asyncio
async def test_keycloak_provider_switching():
    """Тест переключения на Keycloak провайдер"""
    # Создаем экземпляр KeycloakAuthProvider
    keycloak_provider = KeycloakAuthProvider()
    
    # Устанавливаем провайдер
    set_auth_provider(keycloak_provider)
    
    # Проверяем, что провайдер установлен
    assert auth_provider == keycloak_provider


@pytest.mark.asyncio
async def test_builtin_provider_switching():
    """Тест переключения на встроенный провайдер"""
    # Создаем экземпляр BuiltInAuthProvider
    builtin_provider = BuiltInAuthProvider()
    
    # Устанавливаем провайдер
    set_auth_provider(builtin_provider)
    
    # Проверяем, что провайдер установлен
    assert auth_provider == builtin_provider


@pytest.mark.asyncio
async def test_get_current_user_with_keycloak_provider(mock_credentials):
    """Тест получения текущего пользователя с Keycloak провайдером"""
    # Создаем и устанавливаем KeycloakAuthProvider
    keycloak_provider = KeycloakAuthProvider()
    
    # Мокаем метод get_current_user провайдера
    keycloak_provider.get_current_user = Mock()
    keycloak_provider.get_current_user.return_value = {
        "sub": "1",
        "preferred_username": "testuser",
        "email": "testuser@example.com"
    }
    
    set_auth_provider(keycloak_provider)
    
    # Мокаем auth_provider в модуле get_current_user
    with patch('app.core.security.auth_provider', keycloak_provider):
        result = await get_current_user(mock_credentials)
        
        # Проверяем результат
        assert result is not None
        assert result['preferred_username'] == 'testuser'
        assert result['email'] == 'testuser@example.com'


@pytest.mark.asyncio
async def test_get_current_user_with_builtin_provider(mock_credentials):
    """Тест получения текущего пользователя с встроенным провайдером"""
    # Создаем и устанавливаем BuiltInAuthProvider
    builtin_provider = BuiltInAuthProvider()
    
    # Мокаем метод get_current_user провайдера
    builtin_provider.get_current_user = Mock()
    builtin_provider.get_current_user.return_value = {
        "sub": "1",
        "username": "testuser",
        "email": "testuser@example.com",
        "is_active": True,
        "is_superuser": False,
        "roles": ["user"]
    }
    
    set_auth_provider(builtin_provider)
    
    # Мокаем auth_provider в модуле get_current_user
    with patch('app.core.security.auth_provider', builtin_provider):
        result = await get_current_user(mock_credentials)
        
        # Проверяем результат
        assert result is not None
        assert result['username'] == 'testuser'
        assert result['email'] == 'testuser@example.com'
        assert result['is_active'] is True


@pytest.mark.asyncio
async def test_get_current_user_with_no_provider(mock_credentials):
    """Тест получения текущего пользователя без установленного провайдера"""
    # Сбрасываем провайдер
    set_auth_provider(None)
    
    # Проверяем, что возникает исключение
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(mock_credentials)
    
    # Проверяем код ошибки
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_get_current_user_with_invalid_token(mock_credentials):
    """Тест получения текущего пользователя с невалидным токеном"""
    # Создаем и устанавливаем провайдер
    builtin_provider = BuiltInAuthProvider()
    
    # Мокаем метод get_current_user провайдера для возврата None
    builtin_provider.get_current_user = Mock()
    builtin_provider.get_current_user.return_value = None
    
    set_auth_provider(builtin_provider)
    
    # Мокаем auth_provider в модуле get_current_user
    with patch('app.core.security.auth_provider', builtin_provider):
        # Проверяем, что возникает исключение
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_credentials)
        
        # Проверяем код ошибки
        assert exc_info.value.status_code == 401