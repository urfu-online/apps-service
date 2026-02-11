"""Тесты для BuiltInAuthProvider."""
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from app.core.security import BuiltInAuthProvider
from app.models.user import User, Role


@pytest.fixture
def builtin_auth_provider():
    """Фикстура для создания экземпляра BuiltInAuthProvider"""
    return BuiltInAuthProvider()


@pytest.fixture
def mock_user():
    """Фикстура для создания мок-пользователя"""
    user = Mock(spec=User)
    user.id = 1
    user.username = "testuser"
    user.email = "testuser@example.com"
    user.is_active = True
    user.is_superuser = False
    user.hashed_password = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj/RK.PZvO.S"  # bcrypt хэш для "testpass"
    user.roles = [Mock(spec=Role)]
    user.roles[0].name = "user"
    return user


@pytest.mark.asyncio
async def test_builtin_authenticate_success(builtin_auth_provider, mock_user):
    """Тест успешной аутентификации через встроенный провайдер"""
    # Мокаем get_db и bcrypt
    with patch('app.core.security.get_db') as mock_get_db, \
         patch('app.core.security.bcrypt') as mock_bcrypt:
        
        # Настраиваем моки
        mock_db = Mock()
        mock_query = Mock()
        mock_get_db.return_value.__next__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        mock_bcrypt.checkpw.return_value = True
        
        # Выполняем тест
        result = await builtin_auth_provider.authenticate("testuser", "testpass")
        
        # Проверяем результат
        assert result is not None
        assert result['username'] == 'testuser'
        assert result['email'] == 'testuser@example.com'
        assert result['is_active'] is True
        assert 'user' in result['roles']


@pytest.mark.asyncio
async def test_builtin_authenticate_user_not_found(builtin_auth_provider):
    """Тест аутентификации с несуществующим пользователем"""
    # Мокаем get_db
    with patch('app.core.security.get_db') as mock_get_db:
        # Настраиваем моки
        mock_db = Mock()
        mock_query = Mock()
        mock_get_db.return_value.__next__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        # Выполняем тест
        result = await builtin_auth_provider.authenticate("nonexistent", "testpass")
        
        # Проверяем результат
        assert result is None


@pytest.mark.asyncio
async def test_builtin_authenticate_wrong_password(builtin_auth_provider, mock_user):
    """Тест аутентификации с неправильным паролем"""
    # Мокаем get_db и bcrypt
    with patch('app.core.security.get_db') as mock_get_db, \
         patch('app.core.security.bcrypt') as mock_bcrypt:
        
        # Настраиваем моки
        mock_db = Mock()
        mock_query = Mock()
        mock_get_db.return_value.__next__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        mock_bcrypt.checkpw.return_value = False  # Неправильный пароль
        
        # Выполняем тест
        result = await builtin_auth_provider.authenticate("testuser", "wrongpass")
        
        # Проверяем результат
        assert result is None


@pytest.mark.asyncio
async def test_builtin_get_current_user_success(builtin_auth_provider, mock_user):
    """Тест успешного получения текущего пользователя через встроенный провайдер"""
    # Мокаем get_db
    with patch('app.core.security.get_db') as mock_get_db:
        # Настраиваем моки
        mock_db = Mock()
        mock_query = Mock()
        mock_get_db.return_value.__next__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        
        # Выполняем тест
        result = await builtin_auth_provider.get_current_user("1")
        
        # Проверяем результат
        assert result is not None
        assert result['username'] == 'testuser'
        assert result['email'] == 'testuser@example.com'
        assert result['is_active'] is True
        assert 'user' in result['roles']


@pytest.mark.asyncio
async def test_builtin_get_current_user_not_found(builtin_auth_provider):
    """Тест получения текущего пользователя с несуществующим ID"""
    # Мокаем get_db
    with patch('app.core.security.get_db') as mock_get_db:
        # Настраиваем моки
        mock_db = Mock()
        mock_query = Mock()
        mock_get_db.return_value.__next__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        # Выполняем тест
        result = await builtin_auth_provider.get_current_user("999")
        
        # Проверяем результат
        assert result is None


@pytest.mark.asyncio
async def test_builtin_create_user_success(builtin_auth_provider):
    """Тест успешного создания пользователя через встроенный провайдер"""
    # Мокаем get_db и bcrypt
    with patch('app.core.security.get_db') as mock_get_db, \
         patch('app.core.security.bcrypt') as mock_bcrypt:
        
        # Настраиваем моки
        mock_db = Mock()
        mock_query = Mock()
        mock_user = Mock(spec=User)
        mock_user.id = 2
        mock_user.username = "newuser"
        mock_user.email = "newuser@example.com"
        mock_user.is_active = True
        mock_user.is_superuser = False
        mock_user.roles = []
        
        mock_get_db.return_value.__next__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None  # Пользователь не существует
        mock_bcrypt.hashpw.return_value = b"hashed_password"
        mock_db.add = Mock()
        mock_db.commit = Mock()
        mock_db.refresh = Mock()
        mock_db.refresh.side_effect = lambda x: setattr(x, 'id', 2)  # Устанавливаем ID после "сохранения"
        
        # Выполняем тест
        result = await builtin_auth_provider.create_user("newuser", "newpass", ["user"])
        
        # Проверяем результат
        assert result is not None
        assert result['username'] == 'newuser'
        assert result['email'] == 'newuser@example.com'
        assert result['is_active'] is True
        assert 'user' in result['roles']


@pytest.mark.asyncio
async def test_builtin_create_user_already_exists(builtin_auth_provider, mock_user):
    """Тест создания пользователя, который уже существует"""
    # Мокаем get_db
    with patch('app.core.security.get_db') as mock_get_db:
        # Настраиваем моки
        mock_db = Mock()
        mock_query = Mock()
        mock_get_db.return_value.__next__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user  # Пользователь уже существует
        
        # Выполняем тест
        result = await builtin_auth_provider.create_user("testuser", "newpass", ["user"])
        
        # Проверяем результат
        assert result is None