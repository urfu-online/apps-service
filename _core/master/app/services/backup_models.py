"""
Backup models and configuration validation for apps-service-opus.

This module provides:
- Pydantic models for backup configuration validation
- SQLAlchemy models for backup state tracking
- Environment variable validation for Restic credentials
"""

import enum
import os
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import Column, Integer, String, DateTime, BigInteger, Enum as SQLEnum
from sqlalchemy.orm import relationship

from app.models.base import Base


# =============================================================================
# Pydantic Models for Configuration Validation
# =============================================================================

class DatabaseBackupConfig(BaseModel):
    """Configuration for database backup."""
    type: str = Field(..., description="Database type: postgres, mysql, etc.")
    container: str = Field(..., description="Docker container name")
    database: str = Field(..., description="Database name to backup")

    @field_validator('type')
    @classmethod
    def validate_db_type(cls, v: str) -> str:
        allowed_types = {'postgres', 'mysql', 'mariadb', 'mongodb'}
        if v.lower() not in allowed_types:
            raise ValueError(f"Database type must be one of {allowed_types}, got '{v}'")
        return v.lower()


class BackupConfig(BaseModel):
    """
    Pydantic model for backup configuration validation.
    
    Validates:
    - enabled: boolean flag
    - schedule: cron expression (validated by croniter)
    - retention: positive integer
    - paths: list of file paths to backup
    - databases: list of database configurations
    """
    enabled: bool = Field(default=False, description="Enable/disable backups")
    schedule: str = Field(default="0 2 * * *", description="Cron expression for backup schedule")
    retention: int = Field(default=7, gt=0, description="Retention period in days (must be > 0)")
    paths: List[str] = Field(default_factory=list, description="List of file paths to backup")
    databases: List[DatabaseBackupConfig] = Field(default_factory=list, description="List of database configurations")

    @field_validator('schedule')
    @classmethod
    def validate_cron_schedule(cls, v: str) -> str:
        """Validate cron expression using croniter."""
        try:
            from croniter import croniter
            # Try to parse the cron expression
            croniter(v)
        except ImportError:
            # If croniter is not installed, skip validation
            pass
        except Exception as e:
            raise ValueError(f"Invalid cron expression '{v}': {e}")
        return v

    @model_validator(mode='after')
    def validate_restic_env_when_enabled(self) -> 'BackupConfig':
        """
        Validate that RESTIC_REPOSITORY and RESTIC_PASSWORD are set when backup is enabled.
        
        This validator runs after all field validators and checks environment variables.
        """
        if self.enabled:
            restic_repo = os.environ.get('RESTIC_REPOSITORY')
            restic_password = os.environ.get('RESTIC_PASSWORD')

            missing_vars = []
            if not restic_repo:
                missing_vars.append('RESTIC_REPOSITORY')
            if not restic_password:
                missing_vars.append('RESTIC_PASSWORD')

            if missing_vars:
                raise ValueError(
                    f"Backup is enabled but required environment variables are missing: {', '.join(missing_vars)}. "
                    f"Please set these variables before enabling backups."
                )

        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "enabled": True,
                "schedule": "0 2 * * *",
                "retention": 7,
                "paths": ["./data", "./uploads"],
                "databases": [
                    {"type": "postgres", "container": "db", "database": "myservice"}
                ]
            }
        }
    }


def validate_backup_config(enabled: bool = False, **kwargs) -> BackupConfig:
    """
    Helper function to validate backup configuration.
    
    Args:
        enabled: Whether backup is enabled
        **kwargs: Additional configuration parameters
        
    Returns:
        Validated BackupConfig instance
        
    Raises:
        ValueError: If validation fails (e.g., missing env vars when enabled=True)
    """
    config_data = {"enabled": enabled, **kwargs}
    return BackupConfig(**config_data)


# =============================================================================
# SQLAlchemy Models for Backup State Tracking
# =============================================================================

class BackupStatus(str, enum.Enum):
    """Status of a backup operation."""
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class BackupRecord(Base):
    """
    SQLAlchemy model for tracking backup operations.
    
    Stores information about each backup attempt including:
    - Service name
    - Snapshot ID (from Restic or local identifier)
    - Status (running/success/failed)
    - Timestamps
    - Size in bytes
    - Retention policy
    - Local path to backup files
    """
    __tablename__ = "backup_records"

    id = Column(Integer, primary_key=True, index=True)
    service_name = Column(String(255), nullable=False, index=True)
    snapshot_id = Column(String(255), unique=True, index=True, nullable=True)
    status = Column(SQLEnum(BackupStatus), default=BackupStatus.RUNNING, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    size_bytes = Column(BigInteger, default=0, nullable=True)
    retention_days = Column(Integer, default=7, nullable=False)
    local_path = Column(String(1024), nullable=True)
    error_message = Column(String(1024), nullable=True)
    metadata_json = Column(String(4096), nullable=True)

    def __repr__(self) -> str:
        return f"<BackupRecord(id={self.id}, service='{self.service_name}', status='{self.status}')>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary for API responses."""
        return {
            "id": self.id,
            "service_name": self.service_name,
            "snapshot_id": self.snapshot_id,
            "status": self.status.value if isinstance(self.status, BackupStatus) else self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "size_bytes": self.size_bytes,
            "retention_days": self.retention_days,
            "local_path": self.local_path,
            "error_message": self.error_message,
        }
