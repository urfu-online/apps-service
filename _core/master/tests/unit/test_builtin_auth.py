"""Тесты для встроенного провайдера аутентификации."""
import pytest
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from app.models.user import User
from app.core.security import BuiltInAuthProvider


class TestBuiltInAuthProvider:
    """Тесты встроенного провайдера аутентификации."""

    @pytest.fixture
    def mock_auth_provider(self):
        """Фикстура для создания провайдера аутентификации."""
        return BuiltInAuthProvider()

    @pytest.mark.asyncio
    async def test_authenticate_success(self, mock_auth_provider):
        """Тест успешной аутентификации."""
        # Подготавливаем моки
        with patch("app.models.user.User") as MockUser:
            # Мокаем сессию БД
            mock_session = MagicMock()
            mock_query = MagicMock()
            
            mock_user = MagicMock(spec=User)
            mock_user.check_password.return_value = True
            mock_user.to_dict.return_value = {"id": 1, "username": "testuser", "is_active": True}
            
            mock_query.first.return_value = mock_user
            mock_session.query.return_value.filter.return_value = mock_query
            
            with patch("app.core.database.SessionLocal") as mock_session_class:
                mock_session_class.return_value.__enter__.return_value = mock_session
                result = await mock_auth_provider.authenticate("testuser", "correctpassword")

            assert result is not None
            assert result["username"] == "testuser"
            assert result["id"] == 1

    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(self, mock_auth_provider):
        """Тест аутентификации с несуществующим пользователем."""
        with patch("app.models.user.User") as MockUser:
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.first.return_value = None  # Пользователь не найден
            
            mock_session.query.return_value.filter.return_value = mock_query
            
            with patch("app.core.database.SessionLocal") as mock_session_class:
                mock_session_class.return_value.__enter__.return_value = mock_session
                result = await mock_auth_provider.authenticate("nonexistent", "password")
            
            assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_wrong_password(self, mock_auth_provider):
        """Тест аутентификации с неверным паролем."""
        # Мокаем сессию БД
        mock_session = MagicMock()
        mock_query = MagicMock()
        
        mock_user = MagicMock(spec=User)
        mock_user.check_password.return_value = False
        
        mock_query.first.return_value = mock_user
        mock_session.query.return_value.filter.return_value = mock_query
        
        with patch("app.core.database.SessionLocal") as mock_session_class:
            mock_session_class.return_value.__enter__.return_value = mock_session
            result = await mock_auth_provider.authenticate("testuser", "wrongpassword")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_current_user_success(self, mock_auth_provider):
        """Тест получения текущего пользователя по токену."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        
        mock_user = MagicMock(spec=User)
        mock_user.to_dict.return_value = {"id": 1, "username": "testuser", "is_active": True}
        mock_query.first.return_value = mock_user
        
        mock_session.query.return_value.filter.return_value = mock_query
        
        with patch("app.core.database.SessionLocal") as mock_session_class:
            mock_session_class.return_value.__enter__.return_value = mock_session
            result = await mock_auth_provider.get_current_user("1")
        
        assert result is not None
        assert result["username"] == "testuser"
        assert result["id"] == 1

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, mock_auth_provider):
        """Тест получения пользователя с невалидным токеном."""
        # Мокаем сессию БД
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        
        with patch("app.core.database.SessionLocal") as mock_session_class:
            mock_session_class.return_value.__enter__.return_value = mock_session
            result = await mock_auth_provider.get_current_user("invalid_token")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_create_user_success(self, mock_auth_provider):
        """Тест создания пользователя."""
        mock_session = MagicMock()
        # Мокаем проверку существования пользователя (изначально None - не существует)
        mock_session.query.return_value.filter.return_value.first.return_value = None

        # Мокаем новый объект пользователя
        new_user = MagicMock()
        new_user.id = 1
        new_user.username = "newuser"
        new_user.to_dict.return_value = {
            "id": 1,
            "username": "newuser",
            "email": "newuser@example.com",
            "is_active": True,
            "is_superuser": False
        }
        
        with patch("app.models.user.User") as MockUserClass:
            MockUserClass.return_value = new_user
            MockUserClass.username = MagicMock()
            MockUserClass.password = MagicMock()
            MockUserClass.email = MagicMock()
            MockUserClass.is_superuser = MagicMock()
            
            with patch("app.core.database.SessionLocal") as mock_session_class:
                mock_session_class.return_value.__enter__.return_value = mock_session
                result = await mock_auth_provider.create_user("newuser", "password", [])
                
            # Убеждаемся, что добавили пользователя в сессию и зафиксировали
            mock_session.add.assert_called_once_with(new_user)
            mock_session.commit.assert_called_once()
        
        assert result is not None
        assert result["username"] == "newuser"

    @pytest.mark.asyncio
    async def test_create_user_already_exists(self, mock_auth_provider):
        """Тест создания уже существующего пользователя."""
        mock_session = MagicMock()
        existing_user = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = existing_user
        
        with patch("app.core.database.SessionLocal") as mock_session_class:
            mock_session_class.return_value.__enter__.return_value = mock_session
            result = await mock_auth_provider.create_user("existinguser", "password", [])
        
        assert result is None