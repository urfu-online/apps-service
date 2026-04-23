"""
Модели конфигурации резервного копирования для Kopia.
"""
import os
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
import croniter
import datetime


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
        extra="forbid",  # Запрещаем дополнительные поля
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
        """Если enabled=True, проверяет наличие переменных окружения KOPIA."""
        if v:
            repo = os.getenv("KOPIA_REPOSITORY")
            password = os.getenv("KOPIA_REPOSITORY_PASSWORD")
            if not repo or not password:
                raise ValueError(
                    "When backup is enabled, both KOPIA_REPOSITORY and "
                    "KOPIA_REPOSITORY_PASSWORD environment variables must be set"
                )
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