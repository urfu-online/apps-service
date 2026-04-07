from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from keycloak import KeycloakOpenID
from keycloak.exceptions import KeycloakAuthenticationError, KeycloakGetError
from typing import Optional, Dict, Any, List
from abc import ABC, abstractmethod
from sqlalchemy.orm import Session
import bcrypt
import logging

from app.config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer()

# Lazy-инициализация Keycloak клиента
_keycloak_openid: Optional[KeycloakOpenID] = None


def get_keycloak_client():
    """Ленивая инициализация клиента Keycloak."""
    global _keycloak_openid
    if _keycloak_openid is None:
        _keycloak_openid = KeycloakOpenID(
            server_url=str(settings.KEYCLOAK_SERVER_URL),
            client_id=settings.KEYCLOAK_CLIENT_ID,
            realm_name=settings.KEYCLOAK_REALM,
            client_secret_key=settings.KEYCLOAK_CLIENT_SECRET,
        )
    return _keycloak_openid


class AuthProvider(ABC):
    @abstractmethod
    async def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def get_current_user(self, token: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def create_user(self, username: str, password: str, roles: List[str]) -> Optional[Dict[str, Any]]:
        pass


class KeycloakAuthProvider(AuthProvider):
    def __init__(self):
        self.keycloak = get_keycloak_client()

    async def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        try:
            token = self.keycloak.token(username, password)
            userinfo = self.keycloak.userinfo(token["access_token"])
            return dict(userinfo)
        except Exception as e:
            logger.error(f"Keycloak: ошибка аутентификации: {e}")
            return None

    async def get_current_user(self, token: str) -> Optional[Dict[str, Any]]:
        try:
            userinfo = self.keycloak.userinfo(token)
            return dict(userinfo)
        except (KeycloakAuthenticationError, KeycloakGetError) as e:
            logger.error(f"Keycloak: недействительный токен: {e}")
            return None
        except Exception as e:
            logger.error(f"Keycloak: непредвиденная ошибка: {e}")
            return None

    async def create_user(self, username: str, password: str, roles: List[str]) -> Optional[Dict[str, Any]]:
        logger.warning("Создание пользователей не поддерживается в Keycloak через этот интерфейс.")
        return None


class BuiltInAuthProvider(AuthProvider):
    async def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        from app.models.user import User
        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == username, User.is_active == True).first()
            if not user or not user.check_password(password):
                return None
            return user.to_dict()
        except Exception as e:
            logger.error(f"Ошибка аутентификации: {e}")
            return None
        finally:
            db.close()

    async def get_current_user(self, token: str) -> Optional[Dict[str, Any]]:
        from app.models.user import User
        from app.core.database import SessionLocal

        try:
            user_id = int(token)
        except ValueError:
            return None

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
            return user.to_dict() if user else None
        except Exception as e:
            logger.error(f"Ошибка получения пользователя: {e}")
            return None
        finally:
            db.close()

    async def create_user(self, username: str, password: str, roles: List[str]) -> Optional[Dict[str, Any]]:
        from app.models.user import User
        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            if db.query(User).filter(User.username == username).first():
                logger.warning(f"Пользователь {username} уже существует.")
                return None

            user = User(username=username, password=password, is_superuser=False)
            db.add(user)
            db.commit()
            db.refresh(user)
            return user.to_dict()
        except Exception as e:
            logger.error(f"Ошибка создания пользователя: {e}")
            db.rollback()
            return None
        finally:
            db.close()


# Глобальный провайдер
auth_provider: Optional[AuthProvider] = None


def set_auth_provider(provider: AuthProvider) -> None:
    global auth_provider
    auth_provider = provider


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    if not auth_provider:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Аутентификация не инициализирована.")

    user = await auth_provider.get_current_user(credentials.credentials)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверные учётные данные",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user