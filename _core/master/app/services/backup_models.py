"""
Модели конфигурации резервного копирования для Kopia.
"""
import os
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
import croniter
import datetime

logger = logging.getLogger(__name__)


class BackupConfig(BaseModel):
    """Конфигурация резервного копирования для сервиса."""
    
    enabled: bool = False
    schedule: str = "0 2 * * *"  # cron-выражение
    retention_days: int = Field(default=7, ge=1, le=3650)
    paths: List[str] = []
    databases: List[str] = []
    kopia_policy: Dict[str, Any] = Field(
        default_factory=lambda: {
            "keep-daily": 7,
            "keep-weekly": 4,
            "keep-monthly": 6,
            "keep-annual": 2,
        }
    )
    storage_type: str = "filesystem"
    s3_endpoint: Optional[str] = None
    s3_bucket: Optional[str] = None
    
    model_config = ConfigDict(
        # Лишние ключи в секции backup НЕ должны ронять весь манифест:
        # исключение здесь отбрасывало сервис целиком из discovery, и он
        # пропадал из Caddy-маршрутов (инцидент: «сервисы упали на проде»).
        extra="ignore",
        json_schema_extra={
            "example": {
                "enabled": True,
                "schedule": "0 2 * * *",
                "retention_days": 30,
                "paths": ["/data", "/config"],
                "databases": ["postgresql://localhost/mydb"],
                "kopia_policy": {
                    "keep-daily": 7,
                    "keep-weekly": 4,
                    "keep-monthly": 6,
                },
                "storage_type": "filesystem",
                "s3_endpoint": None,
                "s3_bucket": None,
            }
        }
    )
    
    @field_validator("schedule")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        """Проверяет, что schedule является валидным cron-выражением."""
        try:
            croniter.croniter(v, datetime.datetime.now())
        except (croniter.CroniterBadCronError, croniter.CroniterBadDateError) as e:
            raise ValueError(f"Invalid cron expression '{v}': {e}")
        return v
    
    @field_validator("enabled")
    @classmethod
    def validate_env_vars(cls, v: bool, info) -> bool:
        """Если enabled=True, проверяем наличие переменных окружения KOPIA.

        Раньше отсутствие переменных вызывало ValueError, из-за которого ВЕСЬ
        манифест не загружался discovery'ем и сервис пропадал из маршрутов.
        Теперь бэкап мягко отключается с предупреждением, а сервис работает.
        """
        if v:
            repo = os.getenv("KOPIA_REPOSITORY")
            password = os.getenv("KOPIA_REPOSITORY_PASSWORD")
            if not repo or not password:
                logger.warning(
                    "backup.enabled=true, но KOPIA_REPOSITORY/KOPIA_REPOSITORY_PASSWORD "
                    "не заданы — резервное копирование отключено, сервис остаётся в работе"
                )
                return False
        return v
    
    @field_validator("storage_type")
    @classmethod
    def validate_storage_type(cls, v: str) -> str:
        """Проверяет допустимые типы хранилища."""
        allowed = {"filesystem", "s3"}
        if v not in allowed:
            raise ValueError(f"storage_type must be one of {allowed}")
        return v
    
    @model_validator(mode="after")
    def validate_s3_fields(self) -> "BackupConfig":
        """Если storage_type == 's3', проверяет наличие s3_endpoint и s3_bucket."""
        if self.storage_type == "s3":
            if self.s3_endpoint is None:
                raise ValueError("s3_endpoint is required when storage_type is 's3'")
            if self.s3_bucket is None:
                raise ValueError("s3_bucket is required when storage_type is 's3'")
        return self