"""Тесты для endpoints бэкапов Kopia."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.service import Service
from app.models.backup import BackupRecord
from app.services.kopia_backup_manager import KopiaBackupManager


client = TestClient(app)


class TestBackupModels:
    """Тесты Pydantic моделей для бэкапов Kopia."""

    def test_backup_request(self):
        """Тест модели BackupRequest."""
        from app.api.routes.backups import BackupRequest

        request = BackupRequest(dry_run=True, reason="scheduled")
        assert request.dry_run is True
        assert request.reason == "scheduled"

    def test_backup_request_default(self):
        """Тест дефолтного значения BackupRequest."""
        from app.api.routes.backups import BackupRequest

        request = BackupRequest()
        assert request.dry_run is False
        assert request.reason == "manual"

    def test_restore_request(self):
        """Тест модели RestoreRequest."""
        from app.api.routes.backups import RestoreRequest

        request = RestoreRequest(target="/tmp/restore", force=True)
        assert request.target == "/tmp/restore"
        assert request.force is True

    def test_backup_snapshot_response(self):
        """Тест модели BackupSnapshotResponse."""
        from app.api.routes.backups import BackupSnapshotResponse

        dt = datetime.now(timezone.utc)
        response = BackupSnapshotResponse(
            snapshot_id="k123456789",
            service_name="test-service",
            status="completed",
            created_at=dt,
            size_bytes=1024 * 1024,
            retention_days=7,
        )
        assert response.snapshot_id == "k123456789"
        assert response.service_name == "test-service"
        assert response.status == "completed"
        assert response.created_at == dt
        assert response.size_bytes == 1024 * 1024
        assert response.retention_days == 7

    def test_backup_operation_response(self):
        """Тест модели BackupOperationResponse."""
        from app.api.routes.backups import BackupOperationResponse

        response = BackupOperationResponse(
            success=True,
            message="Backup created",
            snapshot_id="k123456789",
            dry_run=False,
            target=None,
        )
        assert response.success is True
        assert response.message == "Backup created"
        assert response.snapshot_id == "k123456789"
        assert response.dry_run is False
        assert response.target is None


class TestBackupEndpoints:
    """Тесты API endpoints для бэкапов Kopia."""

    @pytest.fixture
    def mock_service(self):
        """Мок сервиса с включённым бэкапом."""
        service = MagicMock(spec=Service)
        service.name = "test-service"
        service.backup_config = MagicMock()
        service.backup_config.enabled = True
        return service

    @pytest.fixture
    def mock_backup_manager(self):
        """Мок KopiaBackupManager через app.state.backup."""
        from app.main import app
        with patch.object(app.state, "backup", new=AsyncMock(spec=KopiaBackupManager), create=True) as mock:
            yield mock

    @pytest.fixture
    def mock_discovery(self, mock_service):
        """Мок ServiceDiscovery через app.state.discovery."""
        from app.main import app
        with patch.object(app.state, "discovery", new=MagicMock(), create=True) as mock:
            mock.get_service.return_value = mock_service
            yield mock

    @pytest.fixture
    def mock_auth(self):
        """Мок аутентификации."""
        from unittest.mock import MagicMock, AsyncMock
        mock_provider = MagicMock()
        mock_provider.get_current_user = AsyncMock(return_value={"username": "testuser"})
        with patch("app.core.security.auth_provider", mock_provider):
            with patch("app.core.security.get_current_user", AsyncMock(return_value={"username": "testuser"})) as mock:
                yield mock

    def test_create_backup_success(self, mock_auth, mock_discovery, mock_backup_manager):
        """Успешное создание бэкапа."""
        mock_backup_manager.run_backup.return_value = MagicMock(
            path="k123456789",
            status="completed",
            size_bytes=1024 * 1024,
        )

        response = client.post(
            "/api/backups/test-service/backup",
            json={"dry_run": False, "reason": "manual"},
            headers={"Authorization": "Bearer testtoken"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "snapshot_id" in data
        mock_backup_manager.run_backup.assert_called_once_with("test-service")
        mock_discovery.get_service.assert_called_once_with("test-service")

    def test_create_backup_dry_run(self, mock_auth, mock_discovery, mock_backup_manager):
        """Dry-run создание бэкапа."""
        mock_backup_manager.dry_run_backup.return_value = {
            "snapshot_id": "dry-run-123",
            "status": "dry_run",
            "size_bytes": 0,
        }

        response = client.post(
            "/api/backups/test-service/backup",
            json={"dry_run": True, "reason": "manual"},
            headers={"Authorization": "Bearer testtoken"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["dry_run"] is True
        mock_backup_manager.dry_run_backup.assert_called_once_with("test-service")
        mock_discovery.get_service.assert_called_once_with("test-service")

    def test_create_backup_service_not_found(self, mock_auth, mock_discovery):
        """Сервис не найден."""
        mock_discovery.get_service.return_value = None

        response = client.post(
            "/api/backups/nonexistent/backup",
            json={"dry_run": False},
            headers={"Authorization": "Bearer testtoken"},
        )
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_create_backup_backup_disabled(self, mock_auth, mock_discovery):
        """Бэкапы отключены для сервиса."""
        service = MagicMock(spec=Service)
        service.name = "test-service"
        service.backup_config = MagicMock()
        service.backup_config.enabled = False
        mock_discovery.get_service.return_value = service

        response = client.post(
            "/api/backups/test-service/backup",
            json={"dry_run": False},
            headers={"Authorization": "Bearer testtoken"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "backup disabled" in data["detail"].lower()

    def test_list_backups_success(self, mock_auth, mock_discovery, mock_backup_manager):
        """Успешное получение списка снапшотов."""
        mock_backup_manager.list_snapshots.return_value = [
            {
                "snapshot_id": "k123456789",
                "service_name": "test-service",
                "status": "completed",
                "created_at": datetime.now(timezone.utc),
                "size_bytes": 1024 * 1024,
                "retention_days": 7,
            }
        ]

        response = client.get(
            "/api/backups/test-service",
            headers={"Authorization": "Bearer testtoken"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["snapshot_id"] == "k123456789"
        mock_backup_manager.list_snapshots.assert_called_once_with("test-service")
        mock_discovery.get_service.assert_called_once_with("test-service")

    def test_list_backups_service_not_found(self, mock_auth, mock_discovery):
        """Сервис не найден."""
        mock_discovery.get_service.return_value = None

        response = client.get(
            "/api/backups/nonexistent",
            headers={"Authorization": "Bearer testtoken"},
        )
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_restore_backup_success(self, mock_auth, mock_discovery, mock_backup_manager):
        """Успешное восстановление снапшота."""
        mock_backup_manager.restore_snapshot.return_value = {
            "success": True,
            "message": "Restoration started",
            "operation_id": "op123",
        }

        response = client.post(
            "/api/backups/test-service/restore/k123456789",
            json={"target": "/tmp/restore", "force": True},
            headers={"Authorization": "Bearer testtoken"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Restore completed" in data["message"]
        mock_backup_manager.restore_snapshot.assert_called_once_with(
            "test-service", "k123456789", target="/tmp/restore", force=True
        )
        mock_discovery.get_service.assert_called_once_with("test-service")

    def test_restore_backup_snapshot_not_found(self, mock_auth, mock_discovery, mock_backup_manager):
        """Снапшот не найден."""
        mock_backup_manager.restore_snapshot.side_effect = ValueError("Snapshot not found")

        response = client.post(
            "/api/backups/test-service/restore/invalid-id",
            json={},
            headers={"Authorization": "Bearer testtoken"},
        )
        assert response.status_code == 404
        data = response.json()
        assert "snapshot not found" in data["detail"].lower()
        mock_discovery.get_service.assert_called_once_with("test-service")

    def test_delete_backup_success(self, mock_auth, mock_backup_manager):
        """Успешное удаление снапшота."""
        mock_backup_manager.delete_snapshot.return_value = {
            "success": True,
            "message": "Snapshot deleted",
        }

        response = client.delete(
            "/api/backups/snapshot/k123456789",
            headers={"Authorization": "Bearer testtoken"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        mock_backup_manager.delete_snapshot.assert_called_once_with("k123456789")

    def test_delete_backup_snapshot_not_found(self, mock_auth, mock_backup_manager):
        """Снапшот не найден."""
        mock_backup_manager.delete_snapshot.side_effect = ValueError("Snapshot not found")

        response = client.delete(
            "/api/backups/snapshot/invalid-id",
            headers={"Authorization": "Bearer testtoken"},
        )
        assert response.status_code == 404
        data = response.json()
        assert "snapshot not found" in data["detail"].lower()
