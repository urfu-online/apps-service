from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from keycloak import KeycloakOpenID
from keycloak.exceptions import KeycloakAuthenticationError, KeycloakGetError
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
import logging

from app.config import settings

# Настройка логирования
logger = logging.getLogger(__name__)

# Инициализация Keycloak клиента
keycloak_openid = KeycloakOpenID(
    server_url=settings.KEYCLOAK_SERVER_URL,
    client_id=settings.KEYCLOAK_CLIENT_ID,
    realm_name=settings.KEYCLOAK_REALM,
    client_secret_key=settings.KEYCLOAK_CLIENT_SECRET,
)

# HTTP Bearer токен
security = HTTPBearer()



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


class KeycloakAuthProvider(AuthProvider):
    """Провайдер аутентификации через Keycloak"""
    
    def __init__(self):
        self.keycloak_openid = keycloak_openid
        self.security = security
    
    async def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Аутентификация пользователя через Keycloak
        
        :param username: Имя пользователя
        :param password: Пароль
        :return: Информация о пользователе или None при ошибке
        """
        try:
            # Аутентификация через Keycloak
            token = self.keycloak_openid.token(username, password)
            user_info = self.keycloak_openid.userinfo(token['access_token'])
            return user_info
        except Exception as e:
            logger.error(f"Keycloak authentication error: {e}")
            return None
    
    async def get_current_user(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Получение текущего пользователя из Keycloak токена
        
        :param token: JWT токен
        :return: Информация о пользователе
        """
        try:
            # Декодирование токена (без верификации подписи для простоты)
            # В production следует использовать верификацию
            user_info = self.keycloak_openid.userinfo(token)
            return user_info
        except KeycloakAuthenticationError as e:
            logger.error(f"Keycloak authentication error: {e}")
            return None
        except KeycloakGetError as e:
            logger.error(f"Keycloak get error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during authentication: {e}")
            return None
    
    async def create_user(self, username: str, password: str, roles: list) -> Optional[Dict[str, Any]]:
        """
        Создание нового пользователя в Keycloak
        
        :param username: Имя пользователя
        :param password: Пароль
        :param roles: Список ролей
        :return: Информация о пользователе или None при ошибке
        """
        # Keycloak требует более сложной логики создания пользователей
        # В данном случае возвращаем None, так как это не основная функция
        logger.warning("User creation is not supported for Keycloak provider")
        return None


# Глобальный экземпляр аутентификации
keycloak_auth = KeycloakAuthProvider()


import bcrypt
from sqlalchemy.orm import Session
from app.models import User
from app.core.database import get_db


class BuiltInAuthProvider(AuthProvider):
    """Встроенный провайдер аутентификации с хранением пользователей в БД"""
    
    async def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Аутентификация пользователя по логину и паролю
        
        :param username: Имя пользователя
        :param password: Пароль
        :return: Информация о пользователе или None при ошибке
        """
        try:
            # Получение сессии базы данных
            db = next(get_db())
            
            # Поиск пользователя в базе данных
            user = db.query(User).filter(User.username == username, User.is_active == True).first()
            if not user:
                return None
            
            # Проверка пароля
            if not bcrypt.checkpw(password.encode('utf-8'), user.hashed_password.encode('utf-8')):
                return None
            
            # Возвращаем информацию о пользователе
            return {
                "sub": str(user.id),
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "roles": [role.name for role in user.roles]
            }
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return None
    
    async def get_current_user(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Получение информации о текущем пользователе по токену
        
        :param token: Токен пользователя (в данном случае ID пользователя)
        :return: Информация о пользователе или None при ошибке
        """
        try:
            # Получение сессии базы данных
            db = next(get_db())
            
            # Поиск пользователя в базе данных по ID (токен)
            user = db.query(User).filter(User.id == int(token), User.is_active == True).first()
            if not user:
                return None
            
            # Возвращаем информацию о пользователе
            return {
                "sub": str(user.id),
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "roles": [role.name for role in user.roles]
            }
        except Exception as e:
            logger.error(f"Get current user error: {e}")
            return None
    
    async def create_user(self, username: str, password: str, roles: list) -> Optional[Dict[str, Any]]:
        """
        Создание нового пользователя
        
        :param username: Имя пользователя
        :param password: Пароль
        :param roles: Список ролей
        :return: Информация о пользователе или None при ошибке
        """
        try:
            # Получение сессии базы данных
            db = next(get_db())
            
            # Проверка существования пользователя
            existing_user = db.query(User).filter(User.username == username).first()
            if existing_user:
                logger.warning(f"User {username} already exists")
                return None
            
            # Хэширование пароля
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            # Создание нового пользователя
            user = User(
                username=username,
                hashed_password=hashed_password,
                is_active=True,
                is_superuser=False
            )
            
            # Добавление пользователя в базу данных
            db.add(user)
            db.commit()
            db.refresh(user)
            
            # Возвращаем информацию о пользователе
            return {
                "sub": str(user.id),
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "roles": [role.name for role in user.roles]
            }
        except Exception as e:
            logger.error(f"Create user error: {e}")
            return None


# Глобальный провайдер аутентификации (будет инициализирован в main.py)
auth_provider = None


def set_auth_provider(provider):
    """Установка глобального провайдера аутентификации"""
    global auth_provider
    auth_provider = provider


# Зависимость для получения текущего пользователя
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """
    Зависимость FastAPI для получения текущего пользователя
    
    :param credentials: HTTP Bearer токен
    :return: Информация о пользователе
    """
    if auth_provider is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication provider not initialized",
        )
    
    token = credentials.credentials
    user_info = await auth_provider.get_current_user(token)
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_info