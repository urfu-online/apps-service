from pydantic_settings import BaseSettings
from typing import List, Optional
import os


class Settings(BaseSettings):
    # Основные настройки
    PROJECT_NAME: str = "Platform Master Service"
    PROJECT_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Пути
    SERVICES_PATH: str = "/projects/apps-service-opus/services"
    CADDY_CONFIG_PATH: str = "/projects/apps-service-opus/_core/caddy"
    BACKUP_PATH: str = "/projects/apps-service-opus/backups"
    
    # База данных
    DATABASE_URL: str = "sqlite:///./master.db"
    
    # Keycloak
    KEYCLOAK_SERVER_URL: str = "http://keycloak:8080/auth"
    KEYCLOAK_REALM: str = "platform"
    KEYCLOAK_CLIENT_ID: str = "master-service"
    KEYCLOAK_CLIENT_SECRET: str = ""
    
    # Authentication
    AUTH_PROVIDER: str = "keycloak"  # "keycloak" or "builtin"
    
    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_IDS: List[str] = []
    
    # Restic (бэкапы)
    RESTIC_REPOSITORY: Optional[str] = None
    RESTIC_PASSWORD: Optional[str] = None
    
    # CORS
    ALLOWED_ORIGINS: List[str] = ["*"]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()