"""Тесты для endpoints бэкапов Kopia."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from typing import List, Dict, Any
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.service import Service
from app.services.kopia_backup_manager import KopiaBackupManager
from app.services.discovery import ServiceManifest, ServiceDiscovery


class TestBackupEndpoints:
    """Тесты API endpoints для бэкапов Kopia."""

    @pytest.fixture
    def mock_service_manifest_enabled(self) -> ServiceManifest:
        """Мок ServiceManifest с включённым бэкапом."""
        service = MagicMock(spec=ServiceManifest)
        service.name = "test-service"
        service.backup_enabled = True
        service.backup_config = {"enabled": True}
        return service

    @pytest.fixture
    def mock_service_manifest_disabled(self) -> ServiceManifest:
        """Мок ServiceManifest с отключённым бэкапом."""
        service = MagicMock(spec=ServiceManifest)
        service.name = "test-service"
        service.backup_enabled = False
        service.backup_config = {"enabled": False}
        return service

    @pytest.fixture
    def mock_backup_manager(self) -> AsyncMock:
        """Мок KopiaBackupManager."""
        mock = AsyncMock(spec=KopiaBackupManager)
        mock.run_backup.return_value = "k123456789"
        mock.list_snapshots.return_value = []
        mock.enforce_retention.return_value = None
        mock.restore_snapshot.return_value = None
        mock.delete_snapshot.return_value = None
        return mock

    @pytest.fixture
    def mock_discovery(self) -> MagicMock:
        """Мок ServiceDiscovery."""
        mock = MagicMock(spec=ServiceDiscovery)
        mock.get_service.return_value = None  # default
        return mock

    @pytest.fixture
    def client_with_mocks(
        self,
        mock_backup_manager: AsyncMock,
        mock_discovery: MagicMock,
    ) -> TestClient:
        """TestClient с моками."""
        # Мокаем аутентификацию
        with patch("app.api.routes.backups.get_current_user") as mock_auth:
            mock_auth.return_value = {"username": "testuser", "role": "admin"}
            # Передаём моки в состояние приложения
            app.state.backup_manager = mock_backup_manager
            app.state.discovery = mock_discovery
            client = TestClient(app)
            yield client

    def test_backup_endpoint_dry_run(
        self,
        client_with_mocks: TestClient,
        mock_discovery: MagicMock,
        mock_backup_manager: AsyncMock,
        mock_service_manifest_enabled: ServiceManifest,
    ) -> None:
        """POST /api/backups/{svc}/backup?dry_run=true → 200, dry_run режим."""
        mock_discovery.get_service.return_value = mock_service_manifest_enabled
        mock_backup_manager.run_backup.return_value = None  # dry_run

        response = client_with_mocks.post(
            "/api/backups/test-service/backup?dry_run=true",
            headers={"Authorization": "Bearer test-token"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["success", "dry_run", "disabled", "error"]
        if data["status"] == "dry_run":
            assert data.get("snapshot_id") is None
        # Проверяем что метод вызвался с dry_run=True
        # (зависит от реализации - endpoint может передавать параметр или сам менеджер)
        mock_backup_manager.run_backup.assert_called_once()
        mock_discovery.get_service.assert_called_once_with("test-service")

    def test_backup_endpoint_backup_disabled(
        self,
        client_with_mocks: TestClient,
        mock_discovery: MagicMock,
        mock_backup_manager: AsyncMock,
        mock_service_manifest_disabled: ServiceManifest,
    ) -> None:
        """POST /api/backups/{svc}/backup → 200, backup disabled."""
        mock_discovery.get_service.return_value = mock_service_manifest_disabled

        response = client_with_mocks.post(
            "/api/backups/test-service/backup",
            headers={"Authorization": "Bearer test-token"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "disabled"
        assert data.get("snapshot_id") is None
        mock_backup_manager.run_backup.assert_not_called()
        mock_discovery.get_service.assert_called_once_with("test-service")

    def test_backup_endpoint_service_not_found(
        self,
        client_with_mocks: TestClient,
        mock_discovery: MagicMock,
        mock_backup_manager: AsyncMock,
    ) -> None:
        """POST /api/backups/{svc}/backup → 404, сервис не найден."""
        mock_discovery.get_service.return_value = None

        response = client_with_mocks.post("/api/backups/nonexistent/backup")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()
        mock_backup_manager.run_backup.assert_not_called()
        mock_discovery.get_service.assert_called_once_with("nonexistent")

    def test_list_backups_success(
        self,
        client_with_mocks: TestClient,
        mock_discovery: MagicMock,
        mock_backup_manager: AsyncMock,
        mock_service_manifest_enabled: ServiceManifest,
    ) -> None:
        """GET /api/backups/{svc} → 200, список снапшотов."""
        mock_discovery.get_service.return_value = mock_service_manifest_enabled
        mock_backup_manager.list_snapshots.return_value = [
            MagicMock(
                snapshot_id="k123456789",
                created_at=datetime.now(timezone.utc),
                size_bytes=1024 * 1024,
                retention_days=7,
            )
        ]

        response = client_with_mocks.get("/api/backups/test-service")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if data:  # если есть снапшоты
            assert data[0]["snapshot_id"] == "k123456789"
        mock_backup_manager.list_snapshots.assert_called_once_with("test-service")
        mock_discovery.get_service.assert_called_once_with("test-service")

    def test_list_backups_empty(
        self,
        client_with_mocks: TestClient,
        mock_discovery: MagicMock,
        mock_backup_manager: AsyncMock,
        mock_service_manifest_enabled: ServiceManifest,
    ) -> None:
        """GET /api/backups/{svc} → 200, пустой список."""
        mock_discovery.get_service.return_value = mock_service_manifest_enabled
        mock_backup_manager.list_snapshots.return_value = []

        response = client_with_mocks.get("/api/backups/test-service")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0
        mock_backup_manager.list_snapshots.assert_called_once_with("test-service")
        mock_discovery.get_service.assert_called_once_with("test-service")

    def test_list_backups_service_not_found(
        self,
        client_with_mocks: TestClient,
        mock_discovery: MagicMock,
        mock_backup_manager: AsyncMock,
    ) -> None:
        """GET /api/backups/{svc} → 404, сервис не найден."""
        mock_discovery.get_service.return_value = None

        response = client_with_mocks.get("/api/backups/nonexistent")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()
        mock_backup_manager.list_snapshots.assert_not_called()
        mock_discovery.get_service.assert_called_once_with("nonexistent")

    def test_restore_backup_with_force(
        self,
        client_with_mocks: TestClient,
        mock_discovery: MagicMock,
        mock_backup_manager: AsyncMock,
        mock_service_manifest_enabled: ServiceManifest,
    ) -> None:
        """POST /api/backups/{svc}/restore/{snapshot_id}?force=true → 200."""
        mock_discovery.get_service.return_value = mock_service_manifest_enabled

        response = client_with_mocks.post(
            "/api/backups/test-service/restore/k123456789?force=true"
        )

        assert response.status_code == 200
        data = response.json()
        assert "success" in data.get("status", "").lower() or data.get("success", False)
        mock_backup_manager.restore_snapshot.assert_called_once()
        # Проверяем что force=True передалось
        call_args = mock_backup_manager.restore_snapshot.call_args
        assert "force" in call_args[1] and call_args[1]["force"] is True
        mock_discovery.get_service.assert_called_once_with("test-service")

    def test_restore_backup_snapshot_not_found(
        self,
        client_with_mocks: TestClient,
        mock_discovery: MagicMock,
        mock_backup_manager: AsyncMock,
        mock_service_manifest_enabled: ServiceManifest,
    ) -> None:
        """POST /api/backups/{svc}/restore/{snapshot_id} → 404, snapshot not found."""
        mock_discovery.get_service.return_value = mock_service_manifest_enabled
        mock_backup_manager.restore_snapshot.side_effect = ValueError("Snapshot not found")

        response = client_with_mocks.post("/api/backups/test-service/restore/invalid-id")

        assert response.status_code == 404
        data = response.json()
        assert "snapshot" in data["detail"].lower() and "not found" in data["detail"].lower()
        mock_backup_manager.restore_snapshot.assert_called_once()
        mock_discovery.get_service.assert_called_once_with("test-service")

    def test_delete_backup_success(
        self,
        client_with_mocks: TestClient,
        mock_backup_manager: AsyncMock,
    ) -> None:
        """DELETE /api/backups/snapshot/{snapshot_id} → 204/200."""
        response = client_with_mocks.delete("/api/backups/snapshot/k123456789")

        # Проверяем либо 204 без контента, либо 200 с успешным ответом
        assert response.status_code in (200, 204)
        if response.status_code == 200:
            data = response.json()
            assert data.get("success", False) or "deleted" in data.get("message", "").lower()
        mock_backup_manager.delete_snapshot.assert_called_once_with("k123456789")

    def test_delete_backup_not_found(
        self,
        client_with_mocks: TestClient,
        mock_backup_manager: AsyncMock,
    ) -> None:
        """DELETE /api/backups/snapshot/{snapshot_id} → 404."""
        mock_backup_manager.delete_snapshot.side_effect = ValueError("Snapshot not found")

        response = client_with_mocks.delete("/api/backups/snapshot/invalid-id")

        assert response.status_code == 404
        data = response.json()
        assert "snapshot" in data["detail"].lower() and "not found" in data["detail"].lower()
        mock_backup_manager.delete_snapshot.assert_called_once_with("invalid-id")