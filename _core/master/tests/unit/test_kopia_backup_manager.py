"""Тесты для KopiaBackupManager."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.kopia_backup_manager import KopiaBackupManager
from app.models.backup import Backup


class MockService:
    def __init__(self, name="test-service", visibility="apps"):
        self.id = 1
        self.name = name
        self.visibility = type("V", (), {"value": visibility})()
        self.backup_config = type("C", (), {"enabled": True})()


@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def mock_notifier() -> MagicMock:
    n = MagicMock()
    n.send = AsyncMock()
    n.send_backup_completed = AsyncMock()
    n.send_backup_failed = AsyncMock()
    n.send_retention_pruned = AsyncMock()
    return n


@pytest.fixture
def mgr(mock_db, mock_notifier) -> KopiaBackupManager:
    m = KopiaBackupManager(db=mock_db, notifier=mock_notifier, dry_run=False, subprocess_timeout=10)
    m.scripts_path = Path("/fake/scripts")
    m.kopia_password = "test-password"
    return m


@pytest.fixture
def mgr_dry(mock_db, mock_notifier) -> KopiaBackupManager:
    m = KopiaBackupManager(db=mock_db, notifier=mock_notifier, dry_run=True, subprocess_timeout=10)
    m.scripts_path = Path("/fake/scripts")
    m.kopia_password = "test-password"
    return m


@pytest.fixture
def proc_ok() -> MagicMock:
    p = AsyncMock()
    p.returncode = 0
    p.communicate = AsyncMock(return_value=(
        b"Created snapshot with manifest ID: k123456789\nSnapshot size: 1024 bytes",
        b""
    ))
    return p


@pytest.fixture
def proc_fail() -> MagicMock:
    p = AsyncMock()
    p.returncode = 1
    p.communicate = AsyncMock(return_value=(b"", b"Error: permission denied"))
    return p


# ── RunBackup ──────────────────────────────────────────

class TestRunBackup:

    @pytest.mark.asyncio
    async def test_success(self, mgr, proc_ok):
        svc = MockService()
        res = MagicMock()
        res.scalar_one_or_none.return_value = svc
        mgr.db.execute = AsyncMock(return_value=res)

        with patch("app.services.kopia_backup_manager.Path.exists", return_value=True), \
             patch("asyncio.create_subprocess_exec", return_value=proc_ok), \
             patch.object(mgr, "_copy_service_files", new_callable=AsyncMock):
            result = await mgr.run_backup("test-service")

        assert isinstance(result, Backup)
        assert result.path == "k123456789"

    @pytest.mark.asyncio
    async def test_service_not_found(self, mgr):
        res = MagicMock()
        res.scalar_one_or_none.return_value = None
        mgr.db.execute = AsyncMock(return_value=res)

        with pytest.raises(ValueError, match="not found"):
            await mgr.run_backup("bad")

    @pytest.mark.asyncio
    async def test_disabled(self, mgr):
        svc = MockService()
        svc.backup_config.enabled = False
        res = MagicMock()
        res.scalar_one_or_none.return_value = svc
        mgr.db.execute = AsyncMock(return_value=res)

        with pytest.raises(ValueError, match="disabled"):
            await mgr.run_backup("test-service")

    @pytest.mark.asyncio
    async def test_script_error(self, mgr, proc_fail):
        svc = MockService()
        res = MagicMock()
        res.scalar_one_or_none.return_value = svc
        mgr.db.execute = AsyncMock(return_value=res)

        with patch("app.services.kopia_backup_manager.Path.exists", return_value=True), \
             patch("asyncio.create_subprocess_exec", return_value=proc_fail), \
             patch.object(mgr, "_copy_service_files", new_callable=AsyncMock):
            with pytest.raises(RuntimeError):
                await mgr.run_backup("test-service")

    @pytest.mark.asyncio
    async def test_dry_run(self, mgr_dry):
        svc = MockService()
        res = MagicMock()
        res.scalar_one_or_none.return_value = svc
        mgr_dry.db.execute = AsyncMock(return_value=res)

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            result = await mgr_dry.run_backup("test-service")
            mock_exec.assert_not_called()

        assert isinstance(result, Backup)
        assert result.path == "dry-run-manifest-id"

    @pytest.mark.asyncio
    async def test_timeout(self, mgr):
        svc = MockService()
        res = MagicMock()
        res.scalar_one_or_none.return_value = svc
        mgr.db.execute = AsyncMock(return_value=res)

        # Mock subprocess that hangs
        proc = AsyncMock()
        proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        proc.kill = MagicMock()

        with patch("app.services.kopia_backup_manager.Path.exists", return_value=True), \
             patch("asyncio.create_subprocess_exec", return_value=proc), \
             patch.object(mgr, "_copy_service_files", new_callable=AsyncMock):
            with pytest.raises(RuntimeError, match="timed out"):
                await mgr.run_backup("test-service")


# ── EnforceRetention ──────────────────────────────────────

class TestEnforceRetention:

    @pytest.mark.asyncio
    async def test_success(self, mgr, proc_ok):
        with patch("app.services.kopia_backup_manager.Path.exists", return_value=True), \
             patch("asyncio.create_subprocess_exec", return_value=proc_ok):
            await mgr.enforce_retention("test-service", 7)

    @pytest.mark.asyncio
    async def test_dry_run(self, mgr_dry):
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            await mgr_dry.enforce_retention("test-service", 7)
            mock_exec.assert_not_called()


# ── DryRunBackup ──────────────────────────────────────

class TestDryRunBackup:

    @pytest.mark.asyncio
    async def test_returns_dict(self, mgr):
        svc = MockService()
        res = MagicMock()
        res.scalar_one_or_none.return_value = svc
        mgr.db.execute = AsyncMock(return_value=res)

        result = await mgr.dry_run_backup("test-service")
        assert isinstance(result, dict)
        assert result["dry_run"] is True

    @pytest.mark.asyncio
    async def test_not_found(self, mgr):
        res = MagicMock()
        res.scalar_one_or_none.return_value = None
        mgr.db.execute = AsyncMock(return_value=res)

        result = await mgr.dry_run_backup("bad")
        assert "error" in result


# ── ListSnapshots ──────────────────────────────────────

class TestListSnapshots:

    @pytest.mark.asyncio
    async def test_returns_list(self, mgr):
        rec = MagicMock()
        rec.snapshot_id = "k123"
        rec.service_name = "test-service"
        rec.status = "completed"
        rec.created_at = datetime.now(timezone.utc)
        rec.size_bytes = 1024
        rec.retention_days = 7

        res = MagicMock()
        res.scalars.return_value.all.return_value = [rec]
        mgr.db.execute = AsyncMock(return_value=res)

        result = await mgr.list_snapshots("test-service")
        assert isinstance(result, list)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_empty(self, mgr):
        res = MagicMock()
        res.scalars.return_value.all.return_value = []
        mgr.db.execute = AsyncMock(return_value=res)

        result = await mgr.list_snapshots("test-service")
        assert result == []


# ── RestoreSnapshot ──────────────────────────────────────

class TestRestoreSnapshot:

    @pytest.mark.asyncio
    async def test_success(self, mgr, proc_ok):
        rec = MagicMock()
        rec.snapshot_id = "k123"
        svc = MockService()

        res = MagicMock()
        res.scalar_one_or_none.side_effect = [rec, svc]
        mgr.db.execute = AsyncMock(return_value=res)

        with patch("app.services.kopia_backup_manager.Path.exists", return_value=True), \
             patch("asyncio.create_subprocess_exec", return_value=proc_ok):
            result = await mgr.restore_snapshot("test-service", "k123")

        assert isinstance(result, dict)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_not_found(self, mgr):
        res = MagicMock()
        res.scalar_one_or_none.return_value = None
        mgr.db.execute = AsyncMock(return_value=res)

        with pytest.raises(ValueError, match="not found"):
            await mgr.restore_snapshot("test-service", "k999")


# ── DeleteSnapshot ──────────────────────────────────────

class TestDeleteSnapshot:

    @pytest.mark.asyncio
    async def test_success(self, mgr, proc_ok):
        rec = MagicMock()
        rec.snapshot_id = "k123"
        res = MagicMock()
        res.scalar_one_or_none.return_value = rec
        mgr.db.execute = AsyncMock(return_value=res)

        with patch("app.services.kopia_backup_manager.Path.exists", return_value=True), \
             patch("asyncio.create_subprocess_exec", return_value=proc_ok):
            result = await mgr.delete_snapshot("k123")

        assert isinstance(result, dict)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_not_found(self, mgr):
        res = MagicMock()
        res.scalar_one_or_none.return_value = None
        mgr.db.execute = AsyncMock(return_value=res)

        with pytest.raises(ValueError, match="not found"):
            await mgr.delete_snapshot("k999")


# ── ParseMethods ──────────────────────────────────────

class TestParseMethods:

    def test_parse_manifest_id(self, mgr):
        assert mgr._parse_manifest_id("Created snapshot with manifest ID: k123") == "k123"
        assert mgr._parse_manifest_id("manifest_id: k456") == "k456"
        assert mgr._parse_manifest_id("bad") == "unknown"

    def test_parse_snapshot_size(self, mgr):
        assert mgr._parse_snapshot_size("Snapshot size: 12345 bytes") == 12345
        assert mgr._parse_snapshot_size("no size") == 0
