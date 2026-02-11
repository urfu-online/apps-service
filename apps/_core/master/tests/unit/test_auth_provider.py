"""Тесты для абстрактного интерфейса AuthProvider."""
import pytest
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class AuthProvider(ABC):
    """Абстрактный интерфейс провайдера аутентификации"""
    
    @abstractmethod
    async def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Аутентификация пользователя по логину и паролю"""
        pass
    
    @abstractmethod
    async def get_current_user(self, token: str) -> Optional[Dict[str, Any]]:
        """Получение информации о текущем пользователе по токену"""
        pass
    
    @abstractmethod
    async def create_user(self, username: str, password: str, roles: list) -> Optional[Dict[str, Any]]:
        """Создание нового пользователя"""
        pass


class MockAuthProvider(AuthProvider):
    """Мок реализация AuthProvider для тестирования"""
    
    async def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        # Всегда возвращаем успешный результат для тестов
        return {
            "sub": "1",
            "username": username,
            "email": f"{username}@example.com",
            "is_active": True,
            "is_superuser": False,
            "roles": ["user"]
        }
    
    async def get_current_user(self, token: str) -> Optional[Dict[str, Any]]:
        # Всегда возвращаем успешный результат для тестов
        return {
            "sub": "1",
            "username": "testuser",
            "email": "testuser@example.com",
            "is_active": True,
            "is_superuser": False,
            "roles": ["user"]
        }
    
    async def create_user(self, username: str, password: str, roles: list) -> Optional[Dict[str, Any]]:
        # Всегда возвращаем успешный результат для тестов
        return {
            "sub": "1",
            "username": username,
            "email": f"{username}@example.com",
            "is_active": True,
            "is_superuser": False,
            "roles": roles
        }


@pytest.fixture
def auth_provider():
    """Фикстура для создания экземпляра MockAuthProvider"""
    return MockAuthProvider()


@pytest.mark.asyncio
async def test_auth_provider_abstract_methods():
    """Тест абстрактных методов AuthProvider"""
    # Проверяем, что нельзя создать экземпляр абстрактного класса
    with pytest.raises(TypeError):
        AuthProvider()


@pytest.mark.asyncio
async def test_auth_provider_authenticate(auth_provider):
    """Тест метода authenticate"""
    result = await auth_provider.authenticate("testuser", "testpass")
    assert result is not None
    assert result["username"] == "testuser"
    assert result["email"] == "testuser@example.com"
    assert result["is_active"] is True


@pytest.mark.asyncio
async def test_auth_provider_get_current_user(auth_provider):
    """Тест метода get_current_user"""
    result = await auth_provider.get_current_user("token")
    assert result is not None
    assert result["username"] == "testuser"
    assert result["email"] == "testuser@example.com"
    assert result["is_active"] is True


@pytest.mark.asyncio
async def test_auth_provider_create_user(auth_provider):
    """Тест метода create_user"""
    result = await auth_provider.create_user("newuser", "newpass", ["user", "admin"])
    assert result is not None
    assert result["username"] == "newuser"
    assert result["email"] == "newuser@example.com"
    assert result["is_active"] is True
    assert "user" in result["roles"]
    assert "admin" in result["roles"]