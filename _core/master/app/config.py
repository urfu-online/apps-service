from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, field_validator, Field
from typing import List, Optional
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseSettings):
    # Основные настройки
    PROJECT_NAME: str = Field("Platform Master Service", description="Название сервиса")
    PROJECT_VERSION: str = Field("1.0.0", description="Версия сервиса")
    DEBUG: bool = Field(False, description="Режим отладки")

    # Пути
    SERVICES_PATH: Path = Field(
        ROOT_DIR / "services", description="Путь к каталогу сервисов"
    )
    CADDY_CONFIG_PATH: Path = Field(
        ROOT_DIR / "_core/caddy", description="Путь к конфигурации Caddy"
    )
    BACKUP_PATH: Path = Field(
        ROOT_DIR / "backups", description="Путь к бэкапам"
    )

    # База данных
    DATABASE_URL: str = Field("sqlite:///./master.db", description="URL базы данных")

    # Keycloak
    KEYCLOAK_SERVER_URL: AnyHttpUrl = Field(
        "http://keycloak:8080/auth", description="URL сервера Keycloak"
    )
    KEYCLOAK_REALM: str = Field("platform", description="Realm в Keycloak")
    KEYCLOAK_CLIENT_ID: str = Field(
        "master-service", description="Client ID в Keycloak"
    )
    KEYCLOAK_CLIENT_SECRET: str = Field(
        "", description="Client Secret для аутентификации"
    )

    # Аутентификация
    AUTH_PROVIDER: str = Field(
        "keycloak", description="Провайдер аутентификации: keycloak или builtin"
    )

    # Telegram
    TELEGRAM_BOT_TOKEN: str = Field(
        "", description="Токен Telegram-бота для уведомлений"
    )
    TELEGRAM_CHAT_IDS: List[str] = Field(
        [], description="Список chat_id для отправки уведомлений"
    )

    # Restic (бэкапы)
    RESTIC_REPOSITORY: Optional[str] = Field(
        None, description="Путь/URL репозитория Restic"
    )
    RESTIC_PASSWORD: Optional[str] = Field(
        None, description="Пароль для репозитория Restic"
    )

    # Platform domain (used for Caddy routing)
    PLATFORM_DOMAIN: str = Field(
        "localhost",
        description="Основной домен платформы (например, apps.openedu.urfu.ru)"
    )

    # CORS
    ALLOWED_ORIGINS: List[str] = Field(
        ["*"],
        description="Разрешённые источники CORS (можно использовать '*' для всех)",
    )

    # Безопасность
    SECRET_KEY: str = Field(
        "change-me-in-production", description="Секретный ключ для подписи cookie"
    )

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(",")]
        if isinstance(v, list):
            return v
        raise ValueError(
            "ALLOWED_ORIGINS must be a comma-separated string or a list of strings"
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
