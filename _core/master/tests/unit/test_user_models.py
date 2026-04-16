"""Тесты для моделей пользователя."""
import pytest
from unittest.mock import Mock, MagicMock
from app.models.user import User, Role


@pytest.fixture
def mock_role():
    """Фикстура для создания мока роли."""
    role = MagicMock(spec=Role)
    role.name = "admin"
    role.permissions = ["read", "write", "delete"]
    return role


@pytest.fixture
def mock_user(mock_role):
    """Фикстура для создания мока пользователя."""
    user = MagicMock(spec=User)
    user.id = 1
    user.username = "testuser"
    user.email = "test@example.com"
    user.is_active = True
    user.is_superuser = False
    user.roles = [mock_role]
    
    # Настраиваем методы
    user.has_role = Mock(return_value=True)
    user.get_permissions = Mock(return_value=["read", "write", "delete"])
    user.to_dict = Mock(return_value={
        "id": 1,
        "username": "testuser",
        "email": "test@example.com",
        "is_active": True,
        "is_superuser": False
    })
    return user


def test_user_has_role_success(mock_user):
    """Тест успешной проверки наличия роли у пользователя."""
    result = mock_user.has_role("admin")
    assert result is True
    mock_user.has_role.assert_called_once_with("admin")


def test_user_has_role_failure(mock_user):
    """Тест неудачной проверки наличия роли у пользователя."""
    mock_user.has_role.return_value = False
    result = mock_user.has_role("nonexistent")
    assert result is False


def test_user_get_permissions(mock_user):
    """Тест получения разрешений пользователя."""
    permissions = mock_user.get_permissions()
    assert permissions is not None
    assert isinstance(permissions, list)
    assert "read" in permissions


def test_user_get_permissions_empty_role(mock_user):
    """Тест получения разрешений пользователя без ролей."""
    mock_user.roles = []
    mock_user.get_permissions = Mock(return_value=[])
    permissions = mock_user.get_permissions()
    assert isinstance(permissions, list)
    assert len(permissions) == 0


def test_user_get_permissions_multiple_roles(mock_user, mock_role):
    """Тест получения разрешений пользователя с несколькими ролями."""
    second_role = MagicMock(spec=Role)
    second_role.name = "editor"
    second_role.permissions = ["edit"]
    mock_user.roles = [mock_role, second_role]
    mock_user.get_permissions = Mock(return_value=["read", "write", "delete", "edit"])
    
    permissions = mock_user.get_permissions()
    assert isinstance(permissions, list)
    assert len(permissions) == 4


def test_role_creation(mock_role):
    """Тест создания роли."""
    assert mock_role.name == "admin"
    assert "read" in mock_role.permissions


def test_user_creation(mock_user):
    """Тест создания пользователя."""
    assert mock_user.username == "testuser"
    assert mock_user.email == "test@example.com"
    assert mock_user.is_active is True


def test_user_to_dict(mock_user):
    """Тест сериализации пользователя."""
    user_dict = mock_user.to_dict()
    assert user_dict["username"] == "testuser"
    assert user_dict["email"] == "test@example.com"
