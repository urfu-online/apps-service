"""Тесты для KopiaBackupManager с моками subprocess."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest

from app.services.kopia_backup_manager import KopiaBackupManager, Snapshot


class TestKopiaBackupManager:
    """Тесты KopiaBackupManager с моками asyncio.create_subprocess_exec."""

    @pytest.fixture
    def mock_create_subprocess_exec(self) -> MagicMock:
        """Мок asyncio.create_subprocess_exec."""
        with patch("asyncio.create_subprocess_exec") as mock:
            yield mock

    @pytest.fixture
    def mock_process_success(self) -> MagicMock:
        """Мок успешного процесса с stdout."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        return mock_proc

    @pytest.fixture
    def mock_process_error(self) -> MagicMock:
        """Мок процесса с ошибкой."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        return mock_proc

    @pytest.fixture
    def kopia_manager(self) -> KopiaBackupManager:
        """Экземпляр KopiaBackupManager."""
        manager = KopiaBackupManager()
        manager.scripts_path = Path("/fake/scripts")
        manager.kopia_password = "test-password"
        return manager

    @pytest.mark.asyncio
    async def test_run_backup_success_extract_snapshot_id(
        self,
        kopia_manager: KopiaBackupManager,
        mock_create_subprocess_exec: MagicMock,
        mock_process_success: MagicMock,
    ) -> None:
        """run_backup() → парсинг snapshot_id из stdout kopia."""
        # Настраиваем mock процесса с успешным stdout
        mock_process_success.communicate = AsyncMock(
            return_value=(
                b"Created snapshot with manifest ID: k123456789\nSnapshot size: 1024 bytes\nBackup completed successfully",
                b"",
            )
        )
        mock_create_subprocess_exec.return_value = mock_process_success

        result = await kopia_manager.run_backup("test-service", dry_run=False)

        # Проверяем что snapshot_id был извлечен из stdout
        assert result == "k123456789"
        # Проверяем что скрипт вызывался с правильными параметрами
        mock_create_subprocess_exec.assert_called_once()
        call_args = mock_create_subprocess_exec.call_args[0]
        assert "kopia_backup.sh" in str(call_args[1])
        assert "test-service" in call_args
        assert "test-password" in call_args

    @pytest.mark.asyncio
    async def test_run_backup_dry_run_mode(
        self,
        kopia_manager: KopiaBackupManager,
        mock_create_subprocess_exec: MagicMock,
        mock_process_success: MagicMock,
    ) -> None:
        """run_backup() с dry_run=True должен парсить output."""
        mock_process_success.communicate = AsyncMock(
            return_value=(
                b"DRY RUN: Would create snapshot for test-service\nSnapshot ID would be: k123456789",
                b"",
            )
        )
        mock_create_subprocess_exec.return_value = mock_process_success

        result = await kopia_manager.run_backup("test-service", dry_run=True)

        # В dry_run режиме может возвращаться None или специальное значение
        assert result is None or "dry" in result.lower() or "k123456789" in result
        mock_create_subprocess_exec.assert_called_once()
        # Проверяем наличие флага --dry-run или специального скрипта
        call_args_list = mock_create_subprocess_exec.call_args[0]
        assert any(arg in ["--dry-run", "dry"] for arg in map(str, call_args_list))

    @pytest.mark.asyncio
    async def test_run_backup_script_error_raises_exception(
        self,
        kopia_manager: KopiaBackupManager,
        mock_create_subprocess_exec: MagicMock,
        mock_process_error: MagicMock,
    ) -> None:
        """run_backup() → ошибка скрипта (returncode != 0), проверка exception."""
        mock_process_error.communicate = AsyncMock(
            return_value=(
                b"",
                b"ERROR: Kopia repository not found\nPermission denied\n",
            )
        )
        mock_create_subprocess_exec.return_value = mock_process_error

        with pytest.raises(RuntimeError) as exc_info:
            await kopia_manager.run_backup("test-service")

        assert "failed" in str(exc_info.value).lower() or "error" in str(exc_info.value).lower()
        assert "Permission denied" in str(exc_info.value) or "Kopia" in str(exc_info.value)
        mock_create_subprocess_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_enforce_retention_calls_kopia_policy_script(
        self,
        kopia_manager: KopiaBackupManager,
        mock_create_subprocess_exec: MagicMock,
        mock_process_success: MagicMock,
    ) -> None:
        """enforce_retention() → вызов kopia_policy.sh, обновление БД."""
        mock_process_success.communicate = AsyncMock(return_value=(b"Retention policy applied\nDeleted 5 old snapshots", b""))
        mock_create_subprocess_exec.return_value = mock_process_success

        await kopia_manager.enforce_retention("test-service")

        mock_create_subprocess_exec.assert_called_once()
        call_args = mock_create_subprocess_exec.call_args[0]
        assert "kopia_policy.sh" in str(call_args[1])
        assert "test-service" in call_args
        assert "test-password" in call_args
        # Проверяем наличие параметров для pruning
        assert any(arg in ["--prune", "prune", "--keep-within", "retention"] for arg in map(str, call_args))

    @pytest.mark.asyncio
    async def test_list_snapshots_success(
        self,
        kopia_manager: KopiaBackupManager,
        mock_create_subprocess_exec: MagicMock,
        mock_process_success: MagicMock,
    ) -> None:
        """list_snapshots() возвращает список снапшотов."""
        # Мокаем JSON вывод kopia
        snapshots_json = [
            {
                "id": "k123456789",
                "timestamp": "2024-01-01T12:00:00Z",
                "size_bytes": 1024 * 1024,
                "retention_days": 7,
            },
            {
                "id": "k987654321",
                "timestamp": "2024-01-02T14:30:00Z",
                "size_bytes": 2048 * 1024,
                "retention_days": 14,
            },
        ]
        mock_process_success.communicate = AsyncMock(
            return_value=(json.dumps(snapshots_json).encode("utf-8"), b"")
        )
        mock_create_subprocess_exec.return_value = mock_process_success

        result = await kopia_manager.list_snapshots("test-service")

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0].snapshot_id == "k123456789"
        assert result[1].snapshot_id == "k987654321"
        # Проверяем что вызывался скрипт list snapshots
        mock_create_subprocess_exec.assert_called_once()
        call_args = mock_create_subprocess_exec.call_args[0]
        assert any(arg in ["list", "snapshots"] for arg in map(str, call_args))
        assert "test-service" in call_args

    @pytest.mark.asyncio
    async def test_list_snapshots_empty(
        self,
        kopia_manager: KopiaBackupManager,
        mock_create_subprocess_exec: MagicMock,
        mock_process_success: MagicMock,
    ) -> None:
        """list_snapshots() возвращает пустой список, если нет снапшотов."""
        mock_process_success.communicate = AsyncMock(
            return_value=(json.dumps([]).encode("utf-8"), b"")
        )
        mock_create_subprocess_exec.return_value = mock_process_success

        result = await kopia_manager.list_snapshots("test-service")

        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_list_snapshots_parse_error_returns_empty(
        self,
        kopia_manager: KopiaBackupManager,
        mock_create_subprocess_exec: MagicMock,
        mock_process_success: MagicMock,
    ) -> None:
        """list_snapshots() при ошибке парсинга возвращает пустой список."""
        mock_process_success.communicate = AsyncMock(
            return_value=(b"Invalid JSON output", b"")
        )
        mock_create_subprocess_exec.return_value = mock_process_success

        result = await kopia_manager.list_snapshots("test-service")

        assert isinstance(result, list)
        assert len(result) == 0  # или проверяем что пробрасывается exception, смотря по реализации

    @pytest.mark.asyncio
    async def test_restore_snapshot_with_force(
        self,
        kopia_manager: KopiaBackupManager,
        mock_create_subprocess_exec: MagicMock,
        mock_process_success: MagicMock,
    ) -> None:
        """restore_snapshot() с force=true."""
        mock_process_success.communicate = AsyncMock(
            return_value=(b"Restoration started successfully\nOperation ID: restore-op-123", b"")
        )
        mock_create_subprocess_exec.return_value = mock_process_success

        await kopia_manager.restore_snapshot("test-service", "k123456789", force=True)

        mock_create_subprocess_exec.assert_called_once()
        call_args = mock_create_subprocess_exec.call_args[0]
        assert "k123456789" in call_args
        assert any(arg in ["restore", "snapshot"] for arg in map(str, call_args))
        # Проверяем наличие флага force
        assert any(arg in ["--force", "force", "-f"] for arg in map(str, call_args))

    @pytest.mark.asyncio
    async def test_restore_snapshot_without_force(
        self,
        kopia_manager: KopiaBackupManager,
        mock_create_subprocess_exec: MagicMock,
        mock_process_success: MagicMock,
    ) -> None:
        """restore_snapshot() без force."""
        mock_process_success.communicate = AsyncMock(
            return_value=(b"Restoration started", b"")
        )
        mock_create_subprocess_exec.return_value = mock_process_success

        await kopia_manager.restore_snapshot("test-service", "k123456789", force=False)

        mock_create_subprocess_exec.assert_called_once()
        # Проверяем что нет флага force
        call_args_str = " ".join(map(str, mock_create_subprocess_exec.call_args[0]))
        assert "--force" not in call_args_str and "-f" not in call_args_str

    @pytest.mark.asyncio
    async def test_restore_snapshot_not_found_raises_value_error(
        self,
        kopia_manager: KopiaBackupManager,
        mock_create_subprocess_exec: MagicMock,
        mock_process_error: MagicMock,
    ) -> None:
        """restore_snapshot() при не найденном снапшоте вызывает ValueError."""
        mock_process_error.communicate = AsyncMock(
            return_value=(b"", b"ERROR: Snapshot k123456789 not found\n")
        )
        mock_create_subprocess_exec.return_value = mock_process_error

        with pytest.raises(ValueError) as exc_info:
            await kopia_manager.restore_snapshot("test-service", "k123456789")

        assert "not found" in str(exc_info.value).lower()
        assert "k123456789" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_delete_snapshot_success(
        self,
        kopia_manager: KopiaBackupManager,
        mock_create_subprocess_exec: MagicMock,
        mock_process_success: MagicMock,
    ) -> None:
        """delete_snapshot() успешно удаляет снапшот."""
        mock_process_success.communicate = AsyncMock(
            return_value=(b"Snapshot k123456789 deleted successfully", b"")
        )
        mock_create_subprocess_exec.return_value = mock_process_success

        await kopia_manager.delete_snapshot("k123456789")

        mock_create_subprocess_exec.assert_called_once()
        call_args = mock_create_subprocess_exec.call_args[0]
        assert "k123456789" in call_args
        assert any(arg in ["delete", "remove", "forget"] for arg in map(str, call_args))

    @pytest.mark.asyncio
    async def test_delete_snapshot_not_found_raises_value_error(
        self,
        kopia_manager: KopiaBackupManager,
        mock_create_subprocess_exec: MagicMock,
        mock_process_error: MagicMock,
    ) -> None:
        """delete_snapshot() при не найденном снапшоте вызывает ValueError."""
        mock_process_error.communicate = AsyncMock(
            return_value=(b"", b"ERROR: Cannot delete snapshot k123456789: not found\n")
        )
        mock_create_subprocess_exec.return_value = mock_process_error

        with pytest.raises(ValueError) as exc_info:
            await kopia_manager.delete_snapshot("k123456789")

        assert "not found" in str(exc_info.value).lower()
        assert "k123456789" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_enforce_retention_with_custom_days(
        self,
        kopia_manager: KopiaBackupManager,
        mock_create_subprocess_exec: MagicMock,
        mock_process_success: MagicMock,
    ) -> None:
        """enforce_retention() с кастомным retention_days."""
        mock_process_success.communicate = AsyncMock(return_value=(b"Retention applied for 30 days", b""))
        mock_create_subprocess_exec.return_value = mock_process_success

        await kopia_manager.enforce_retention("test-service", retention_days=30)

        mock_create_subprocess_exec.assert_called_once()
        call_args_str = " ".join(map(str, mock_create_subprocess_exec.call_args[0]))
        # Проверяем что передаётся retention_days
        assert "30" in call_args_str or "retention" in call_args_str

    @pytest.mark.asyncio
    async def test_run_backup_script_timeout_handling(
        self,
        kopia_manager: KopiaBackupManager,
        mock_create_subprocess_exec: MagicMock,
    ) -> None:
        """run_backup() обрабатывает timeout при выполнении скрипта."""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError("Script execution timeout"))
        mock_create_subprocess_exec.return_value = mock_proc

        with pytest.raises(RuntimeError) as exc_info:
            await kopia_manager.run_backup("test-service")

        assert "timeout" in str(exc_info.value).lower() or "timed out" in str(exc_info.value).lower()