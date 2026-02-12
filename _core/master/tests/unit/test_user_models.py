"""Тесты для моделей пользователей."""
import pytest
from unittest.mock import Mock
from app.models.user import User, Role


@pytest.fixture
def mock_role():
    """Фикстура для создания мок-роли"""
    role = Mock(spec=Role)
    role.name = "admin"
    role.permissions = "read,write,delete"
    return role


@pytest.fixture
def mock_user(mock_role):
    """Фикстура для создания мок-пользователя"""
    user = Mock(spec=User)
    user.id = 1
    user.username = "testuser"
    user.email = "testuser@example.com"
    user.is_active = True
    user.is_superuser = False
    user.roles = [mock_role]
    return user


def test_user_has_role_success(mock_user):
    """Тест успешной проверки наличия роли у пользователя"""
    # Выполняем тест
    result = mock_user.has_role("admin")
    
    # Проверяем результат
    assert result is True


def test_user_has_role_failure(mock_user):
    """Тест неудачной проверки наличия роли у пользователя"""
    # Выполняем тест
    result = mock_user.has_role("nonexistent")
    
    # Проверяем результат
    assert result is False


def test_user_get_permissions(mock_user, mock_role):
    """Тест получения разрешений пользователя"""
    # Выполняем тест
    permissions = mock_user.get_permissions()
    
    # Проверяем результат
    assert permissions is not None
    assert isinstance(permissions, list)
    assert "read" in permissions
    assert "write" in permissions
    assert "delete" in permissions


def test_user_get_permissions_empty_role(mock_user):
    """Тест получения разрешений пользователя с пустой ролью"""
    # Создаем роль без разрешений
    empty_role = Mock(spec=Role)
    empty_role.name = "user"
    empty_role.permissions = None
    
    # Устанавливаем пользователю пустую роль
    mock_user.roles = [empty_role]
    
    # Выполняем тест
    permissions = mock_user.get_permissions()
    
    # Проверяем результат
    assert permissions is not None
    assert isinstance(permissions, list)
    assert len(permissions) == 0


def test_user_get_permissions_multiple_roles(mock_user):
    """Тест получения разрешений пользователя с несколькими ролями"""
    # Создаем вторую роль
    second_role = Mock(spec=Role)
    second_role.name = "editor"
    second_role.permissions = "read,write"
    
    # Добавляем вторую роль пользователю
    mock_user.roles.append(second_role)
    
    # Выполняем тест
    permissions = mock_user.get_permissions()
    
    # Проверяем результат (дубликаты должны быть удалены)
    assert permissions is not None
    assert isinstance(permissions, list)
    assert "read" in permissions
    assert "write" in permissions
    assert "delete" in permissions
    # Проверяем, что нет дубликатов
    assert len(permissions) == 3


def test_role_creation():
    """Тест создания роли"""
    # Создаем роль
    role = Role(
        id=1,
        name="admin",
        description="Administrator role",
        permissions="read,write,delete"
    )
    
    # Проверяем атрибуты
    assert role.id == 1
    assert role.name == "admin"
    assert role.description == "Administrator role"
    assert role.permissions == "read,write,delete"


def test_user_creation():
    """Тест создания пользователя"""
    # Создаем пользователя
    user = User(
        id=1,
        username="testuser",
        email="testuser@example.com",
        hashed_password="hashed_password",
        is_active=True,
        is_superuser=False
    )
    
    # Проверяем атрибуты
    assert user.id == 1
    assert user.username == "testuser"
    assert user.email == "testuser@example.com"
    assert user.hashed_password == "hashed_password"
    assert user.is_active is True
    assert user.is_superuser is False
    # Проверяем, что роли пусты
    assert user.roles == []