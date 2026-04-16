"""Тесты для endpoints бэкапов - Pydantic модели."""
import pytest
from datetime import datetime, timezone


class TestBackupModels:
    """Тесты Pydantic моделей для бэкапов."""

    def test_backup_response(self):
        """Тест модели BackupResponse."""
        from app.api.routes.backups import BackupResponse
        
        response = BackupResponse(
            id=1,
            service_id=1,
            name="backup_20240101",
            timestamp=datetime.now(timezone.utc),
            size=1024,
            status="completed",
            reason="manual"
        )
        
        assert response.id == 1
        assert response.name == "backup_20240101"
        assert response.status == "completed"
        assert response.reason == "manual"

    def test_backup_create_request(self):
        """Тест модели BackupCreateRequest."""
        from app.api.routes.backups import BackupCreateRequest
        
        request = BackupCreateRequest(reason="scheduled")
        assert request.reason == "scheduled"

    def test_backup_create_request_default(self):
        """Тест дефолтного значения BackupCreateRequest."""
        from app.api.routes.backups import BackupCreateRequest
        
        request = BackupCreateRequest()
        assert request.reason == "manual"

    def test_restore_request(self):
        """Тест модели RestoreRequest."""
        from app.api.routes.backups import RestoreRequest
        
        request = RestoreRequest(backup_id=1)
        assert request.backup_id == 1
