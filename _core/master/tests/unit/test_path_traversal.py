"""Тесты защиты от path traversal в restore (шаг 3 плана исправлений)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_manager():
    from app.services.kopia_backup_manager import KopiaBackupManager

    mgr = MagicMock(spec=KopiaBackupManager)
    # используем реальный метод restore_snapshot
    mgr.restore_snapshot = KopiaBackupManager.restore_snapshot.__get__(mgr, KopiaBackupManager)
    mgr.db = AsyncMock()
    mgr.dry_run = False
    mgr.scripts_path = Path("/tmp/kopia-scripts")
    mgr.kopia_password = ""
    return mgr


async def _setup_existing_snapshot(mgr, service_name="myapp"):
    """Настраивает моки БД так, что снапшот и сервис существуют."""
    record = MagicMock()
    record.snapshot_id = "kabc123"
    service = MagicMock()
    service.name = service_name
    service.visibility.value = "public"
    service.backup_config.enabled = True

    async def fake_execute(stmt):
        res = MagicMock()
        s = str(stmt)
        if "BackupRecord" in s:
            res.scalar_one_or_none = MagicMock(return_value=record)
        else:
            res.scalar_one_or_none = MagicMock(return_value=service)
        return res

    mgr.db.execute = fake_execute
    return service


@pytest.mark.parametrize(
    "target",
    [
        "/etc",
        "/etc/passwd",
        "../../etc/passwd",
        "/projects/apps-service-opus/services/../etc",
    ],
)
async def test_restore_rejects_path_traversal(target):
    mgr = _make_manager()
    await _setup_existing_snapshot(mgr)

    with pytest.raises(ValueError, match="target must be under"):
        await mgr.restore_snapshot("myapp", "kabc123", target=target, force=True)


async def test_restore_accepts_valid_target():
    mgr = _make_manager()
    service = await _setup_existing_snapshot(mgr)

    valid = f"/projects/apps-service-opus/services/{service.visibility.value}/{service.name}"

    with patch("app.config.settings") as cfg, patch(
        "asyncio.create_subprocess_exec"
    ) as mock_exec, patch("os.path.exists", return_value=True):
        cfg.SERVICES_PATH = "/projects/apps-service-opus/services"
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"ok", b""))
        mock_exec.return_value = proc
        # скрипт должен существовать
        with patch.object(Path, "exists", return_value=True):
            result = await mgr.restore_snapshot(
                "myapp", "kabc123", target=valid, force=True
            )
    assert result["success"] is True
