"""
Тесты для конфигурации резервного копирования (BackupConfig).
"""
import os
import pytest
from unittest.mock import patch
from pydantic import ValidationError
from app.services.backup_models import BackupConfig


def test_backup_config_defaults():
    """Тест создания BackupConfig с enabled=False (дефолтные значения)."""
    config = BackupConfig(enabled=False)
    assert config.enabled is False
    assert config.schedule == "0 2 * * *"
    assert config.retention_days == 7
    assert config.paths == []
    assert config.databases == []
    assert config.kopia_policy == {
        "keep-daily": 7,
        "keep-weekly": 4,
        "keep-monthly": 6,
        "keep-annual": 2,
    }
    assert config.storage_type == "filesystem"
    assert config.s3_endpoint is None
    assert config.s3_bucket is None


def test_backup_config_custom_values(monkeypatch):
    """Тест создания BackupConfig с пользовательскими значениями."""
    monkeypatch.setenv("KOPIA_REPOSITORY", "/path/to/repo")
    monkeypatch.setenv("KOPIA_REPOSITORY_PASSWORD", "secret")
    config = BackupConfig(
        enabled=True,
        schedule="*/5 * * * *",
        retention_days=30,
        paths=["/data", "/config"],
        databases=["postgresql://localhost/mydb"],
        kopia_policy={"keep-daily": 3},
        storage_type="s3",
        s3_endpoint="https://s3.example.com",
        s3_bucket="my-backups",
    )
    assert config.enabled is True
    assert config.schedule == "*/5 * * * *"
    assert config.retention_days == 30
    assert config.paths == ["/data", "/config"]
    assert config.databases == ["postgresql://localhost/mydb"]
    assert config.kopia_policy == {"keep-daily": 3}
    assert config.storage_type == "s3"
    assert config.s3_endpoint == "https://s3.example.com"
    assert config.s3_bucket == "my-backups"


def test_backup_config_invalid_cron():
    """Тест валидации некорректного cron-выражения."""
    with pytest.raises(ValueError, match="Invalid cron expression"):
        BackupConfig(schedule="invalid-cron")


def test_backup_config_valid_cron():
    """Тест валидации корректного cron-выражения."""
    config = BackupConfig(schedule="0 */6 * * *")
    assert config.schedule == "0 */6 * * *"


def test_backup_config_enabled_without_env_vars(monkeypatch):
    """Тест валидации с enabled=True и отсутствующими KOPIA переменными окружения."""
    # Убедимся, что переменные не установлены
    monkeypatch.delenv("KOPIA_REPOSITORY", raising=False)
    monkeypatch.delenv("KOPIA_REPOSITORY_PASSWORD", raising=False)
    
    with pytest.raises(ValueError, match="KOPIA_REPOSITORY and KOPIA_REPOSITORY_PASSWORD"):
        BackupConfig(enabled=True)


def test_backup_config_enabled_with_env_vars(monkeypatch):
    """Тест валидации с enabled=True и установленными KOPIA переменными."""
    monkeypatch.setenv("KOPIA_REPOSITORY", "/path/to/repo")
    monkeypatch.setenv("KOPIA_REPOSITORY_PASSWORD", "secret")
    
    config = BackupConfig(enabled=True)
    assert config.enabled is True


def test_backup_config_disabled_ignores_env_vars(monkeypatch):
    """Тест, что при enabled=False переменные окружения не проверяются."""
    # Переменные не установлены, но конфиг должен создаться
    monkeypatch.delenv("KOPIA_REPOSITORY", raising=False)
    monkeypatch.delenv("KOPIA_REPOSITORY_PASSWORD", raising=False)
    
    config = BackupConfig(enabled=False)
    assert config.enabled is False


def test_backup_config_storage_type_validation(monkeypatch):
    """Тест валидации storage_type."""
    monkeypatch.setenv("KOPIA_REPOSITORY", "/path/to/repo")
    monkeypatch.setenv("KOPIA_REPOSITORY_PASSWORD", "secret")
    # Допустимые значения
    config1 = BackupConfig(storage_type="filesystem")
    assert config1.storage_type == "filesystem"
    
    config2 = BackupConfig(
        storage_type="s3",
        s3_endpoint="https://example.com",
        s3_bucket="bucket",
        enabled=False  # чтобы не требовались env переменные
    )
    assert config2.storage_type == "s3"
    
    # Недопустимое значение
    with pytest.raises(ValueError, match="storage_type must be one of"):
        BackupConfig(storage_type="invalid")


def test_backup_config_s3_fields_required():
    """Тест, что s3_endpoint и s3_bucket обязательны при storage_type='s3'."""
    with pytest.raises(ValueError, match="s3_endpoint is required"):
        BackupConfig(storage_type="s3", s3_bucket="bucket")
    
    with pytest.raises(ValueError, match="s3_bucket is required"):
        BackupConfig(storage_type="s3", s3_endpoint="https://example.com")
    
    # Оба поля присутствуют - OK
    config = BackupConfig(
        storage_type="s3",
        s3_endpoint="https://example.com",
        s3_bucket="bucket"
    )
    assert config.s3_endpoint == "https://example.com"
    assert config.s3_bucket == "bucket"


def test_backup_config_s3_fields_ignored_for_filesystem():
    """Тест, что s3_endpoint и s3_bucket игнорируются при storage_type='filesystem'."""
    config = BackupConfig(
        storage_type="filesystem",
        s3_endpoint="https://example.com",
        s3_bucket="bucket"
    )
    # Поля сохраняются, но не валидируются как обязательные
    assert config.s3_endpoint == "https://example.com"
    assert config.s3_bucket == "bucket"


def test_backup_config_extra_fields_forbidden():
    """Тест, что дополнительные поля запрещены."""
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        BackupConfig(unknown_field="value")


def test_backup_config_retention_days_range():
    """Тест валидации диапазона retention_days."""
    # Нижняя граница
    config = BackupConfig(retention_days=1)
    assert config.retention_days == 1
    
    # Верхняя граница
    config = BackupConfig(retention_days=3650)
    assert config.retention_days == 3650
    
    # Ниже границы
    with pytest.raises(ValidationError, match="Input should be greater than or equal to 1"):
        BackupConfig(retention_days=0)
    
    # Выше границы
    with pytest.raises(ValidationError, match="Input should be less than or equal to 3650"):
        BackupConfig(retention_days=3651)