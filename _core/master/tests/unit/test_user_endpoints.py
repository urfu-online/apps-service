"""Тесты для endpoints пользователей - CRUD полные тесты."""
import pytest
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from fastapi import HTTPException
from app.models.user import User
from app.api.routes.users import router, create_user, get_user, update_user, delete_user, list_users


class TestUserEndpointsFullCRUD:
    """Полные CRUD тесты для endpoints пользователей."""

    @pytest.mark.asyncio
    async def test_create_user_success(self):
        """Тест создания нового пользователя."""
        # Подготовка параметров
        username = "testuser"
        password = "password"
        email = "test@example.com"
        is_superuser = False
        
        # Создаем мок для текущего пользователя администратора
        current_user = {"sub": "1", "is_superuser": True}
        
        # Подготовим мок-сессию БД
        db_mock = MagicMock()
        
        # Подготовим мок-пользователя который будет возвращен после создания
        user_data = {
            "id": 1,
            "username": username,
            "email": email,
            "is_active": True,
            "is_superuser": is_superuser
        }
        
        user_mock = MagicMock(spec=User)
        user_mock.id = 1
        user_mock.username = username
        user_mock.email = email
        user_mock.is_active = True
        user_mock.is_superuser = is_superuser
        
        # Настраиваем провайдер аутентификации
        with patch("app.api.routes.users.BuiltInAuthProvider") as AuthProviderMock:
            auth_provider_instance = MagicMock()
            auth_provider_instance.create_user = AsyncMock(return_value=user_data)
            
            AuthProviderMock.return_value = auth_provider_instance
            
            # Настраиваем моки для проверки существования пользователя (сначала None - пользователь не существует)
            db_mock.query.return_value.filter.return_value.first.return_value = None
            
            # Выполнение запроса
            result = await create_user(
                username=username,
                password=password,
                email=email,
                is_superuser=is_superuser,
                current_user=current_user,
                db=db_mock
            )
            
            # Проверки
            assert "message" in result
            assert result["message"] == "User created successfully"
            assert "user" in result
            assert result["user"]["username"] == username
            
            # Проверка вызова создания пользователя
            auth_provider_instance.create_user.assert_called_once_with(username, password, [])
            
            # Проверка обновления дополнительных полей
            assert user_mock.email == email
            assert user_mock.is_superuser == is_superuser
            db_mock.commit.assert_called()

    @pytest.mark.asyncio
    async def test_create_user_already_exists(self):
        """Тест создания уже существующего пользователя."""
        # Подготовка параметров
        username = "existinguser"
        password = "password"
        email = "exists@example.com"
        is_superuser = False
        
        # Создаем мок для текущего пользователя администратора
        current_user = {"sub": "1", "is_superuser": True}
        
        # Подготовим мок-сессию БД
        db_mock = MagicMock()
        
        # Подготовим мок существующего пользователя
        existing_user_mock = MagicMock()
        db_mock.query.return_value.filter.return_value.first.return_value = existing_user_mock
        
        # Тестируем HTTPException при попытке создать существующего пользователя
        with pytest.raises(HTTPException) as exc_info:
            await create_user(
                username=username,
                password=password,
                email=email,
                is_superuser=is_superuser,
                current_user=current_user,
                db=db_mock
            )
            
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "User already exists"

    @pytest.mark.asyncio
    async def test_create_user_insufficient_permissions(self):
        """Тест создания пользователя без достаточных прав."""
        # Подготовка параметров
        username = "newuser"
        password = "password"
        email = "new@example.com"
        is_superuser = False
        
        # Создаем мок для текущего пользователя без прав администратора
        current_user = {"sub": "2", "is_superuser": False}
        
        # Подготовим мок-сессию БД
        db_mock = MagicMock()
        
        # Тестируем HTTPException при недостаточных правах
        with pytest.raises(HTTPException) as exc_info:
            await create_user(
                username=username,
                password=password,
                email=email,
                is_superuser=is_superuser,
                current_user=current_user,
                db=db_mock
            )
            
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Not enough permissions"

    @pytest.mark.asyncio
    async def test_get_user_success(self):
        """Тест получения информации о пользователе."""
        user_id = 1
        current_user = {"sub": "1", "is_superuser": True}
        
        # Подготовим мок-пользователя
        user_mock = MagicMock(spec=User)
        user_mock.id = user_id
        user_mock.username = "testuser"
        user_mock.email = "test@example.com"
        
        # Подготовим мок-сессию БД
        db_mock = MagicMock()
        db_mock.query.return_value.filter.return_value.first.return_value = user_mock
        
        result = await get_user(user_id=user_id, current_user=current_user, db=db_mock)
        
        assert result.id == user_id
        assert result.username == "testuser"
        assert result.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_user_not_found(self):
        """Тест получения несуществующего пользователя."""
        user_id = 999
        current_user = {"sub": "1", "is_superuser": True}
        
        # Подготовим мок-сессию БД (пользователь не найден)
        db_mock = MagicMock()
        db_mock.query.return_value.filter.return_value.first.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await get_user(user_id=user_id, current_user=current_user, db=db_mock)
            
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "User not found"

    @pytest.mark.asyncio
    async def test_get_user_insufficient_permissions(self):
        """Тест получения информации о пользователе с недостаточными правами."""
        user_id = 2  # ID другого пользователя
        current_user = {"sub": "1", "is_superuser": False}  # Не суперпользователь
        
        # Подготовим мок-пользователя
        user_mock = MagicMock(spec=User)
        user_mock.id = user_id
        user_mock.username = "otheruser"
        user_mock.email = "other@example.com"
        
        # Подготовим мок-сессию БД
        db_mock = MagicMock()
        db_mock.query.return_value.filter.return_value.first.return_value = user_mock
        
        with pytest.raises(HTTPException) as exc_info:
            await get_user(user_id=user_id, current_user=current_user, db=db_mock)
            
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Not enough permissions"

    @pytest.mark.asyncio
    async def test_update_user_success(self):
        """Тест обновления информации о пользователе."""
        user_id = 1
        username = "updateduser"
        email = "updated@example.com"
        is_active = True
        is_superuser = True
        
        current_user = {"sub": "1", "is_superuser": True}
        
        # Подготовим мок-пользователя
        user_mock = MagicMock(spec=User)
        user_mock.id = user_id
        user_mock.username = "olduser"
        user_mock.email = "old@example.com"
        user_mock.is_active = False
        user_mock.is_superuser = False
        
        # Подготовим мок-сессию БД
        db_mock = MagicMock()
        db_mock.query.return_value.filter.return_value.first.return_value = user_mock
        
        result = await update_user(
            user_id=user_id,
            username=username,
            email=email,
            is_active=is_active,
            is_superuser=is_superuser,
            current_user=current_user,
            db=db_mock
        )
        
        assert "message" in result
        assert result["message"] == "User updated successfully"
        
        assert user_mock.username == username
        assert user_mock.email == email
        assert user_mock.is_active == is_active
        assert user_mock.is_superuser == is_superuser
        
        db_mock.commit.assert_called()
        db_mock.refresh.assert_called_once_with(user_mock)

    @pytest.mark.asyncio
    async def test_update_user_not_found(self):
        """Тест обновления несуществующего пользователя."""
        user_id = 999
        username = "updateduser"
        
        current_user = {"sub": "1", "is_superuser": True}
        
        # Подготовим мок-сессию БД (пользователь не найден)
        db_mock = MagicMock()
        db_mock.query.return_value.filter.return_value.first.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await update_user(
                user_id=user_id,
                username=username,
                current_user=current_user,
                db=db_mock
            )
            
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "User not found"

    @pytest.mark.asyncio
    async def test_delete_user_success(self):
        """Тест удаления пользователя."""
        user_id = 1
        current_user = {"sub": "1", "is_superuser": True}
        
        # Подготовим мок-пользователя
        user_mock = MagicMock(spec=User)
        user_mock.id = user_id
        user_mock.username = "todelete"
        
        # Подготовим мок-сессию БД
        db_mock = MagicMock()
        db_mock.query.return_value.filter.return_value.first.return_value = user_mock
        
        result = await delete_user(user_id=user_id, current_user=current_user, db=db_mock)
        
        assert "message" in result
        assert result["message"] == "User deleted successfully"
        
        db_mock.delete.assert_called_once_with(user_mock)
        db_mock.commit.assert_called()

    @pytest.mark.asyncio
    async def test_list_users_success(self):
        """Тест получения списка пользователей."""
        current_user = {"sub": "1", "is_superuser": True}
        
        # Подготовим мок-пользователей
        user1 = MagicMock(spec=User)
        user1.id = 1
        user1.username = "user1"
        user1.email = "user1@example.com"
        
        user2 = MagicMock(spec=User)
        user2.id = 2
        user2.username = "user2"
        user2.email = "user2@example.com"
        
        # Подготовим мок-сессию БД
        db_mock = MagicMock()
        db_mock.query.return_value.all.return_value = [user1, user2]
        
        result = await list_users(current_user=current_user, db=db_mock)
        
        assert len(result) == 2
        assert result[0].username == "user1"
        assert result[1].username == "user2"