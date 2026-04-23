"""Тесты для BackupAPIClient (aiohttp + tenacity)."""

import asyncio
from typing import Dict, Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import aiohttp
from aiohttp import ClientSession, ClientTimeout
from tenacity import RetryError

from platform_cli.api.backup_client import BackupAPIClient, BackupResponse, APIClientError


class TestBackupAPIClient:
    """Тесты для Async HTTP клиента с ретраями."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Мок aiohttp.ClientSession."""
        session = AsyncMock(spec=ClientSession)
        session._request = AsyncMock()
        session.request = AsyncMock()
        session.close = AsyncMock()
        return session

    @pytest.fixture
    def api_client(self, mock_session: AsyncMock) -> BackupAPIClient:
        """Экземпляр BackupAPIClient с моком сессии."""
        client = BackupAPIClient(base_url="http://localhost:8000", api_key="test-key")
        client._session = mock_session
        return client

    @pytest.fixture
    def backup_response_success(self) -> Dict[str, Any]:
        """Успешный ответ бэкапа."""
        return {
            "snapshot_id": "k123456789",
            "status": "success",
            "message": "Backup created",
            "dry_run": False,
        }

    @pytest.fixture
    def backup_response_dry_run(self) -> Dict[str, Any]:
        """Ответ dry_run режима."""
        return {
            "snapshot_id": None,
            "status": "dry_run",
            "message": "Dry run completed",
            "dry_run": True,
        }

    @pytest.fixture
    def backup_response_disabled(self) -> Dict[str, Any]:
        """Ответ с отключённым бэкапом."""
        return {
            "snapshot_id": None,
            "status": "disabled",
            "message": "Backup disabled for service",
            "dry_run": False,
        }

    @pytest.fixture
    def backup_response_error(self) -> Dict[str, Any]:
        """Ответ с ошибкой."""
        return {
            "snapshot_id": None,
            "status": "error",
            "message": "Failed to create backup",
            "error": "Permission denied",
        }

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_session: AsyncMock) -> None:
        """Контекстный менеджер создаёт и закрывает сессию."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session_instance = AsyncMock()
            mock_session_class.return_value = mock_session_instance

            async with BackupAPIClient(base_url="http://localhost:8000") as client:
                assert client._session == mock_session_instance
                assert isinstance(client, BackupAPIClient)

            mock_session_instance.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_success(
        self, api_client: BackupAPIClient, mock_session: AsyncMock, backup_response_success: Dict[str, Any]
    ) -> None:
        """Успешный запрос возвращает данные."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=backup_response_success)
        mock_response.__aenter__.return_value = mock_response
        mock_response.__aexit__.return_value = None

        mock_session.request.return_value = mock_response

        result = await api_client.request("POST", "/api/backups/test/backup")

        assert result == backup_response_success
        mock_session.request.assert_called_once_with(
            "POST",
            "http://localhost:8000/api/backups/test/backup",
            headers={"Authorization": "Bearer test-key"},
            json=None,
            timeout=ClientTimeout(total=30),
        )

    @pytest.mark.asyncio
    async def test_request_with_json_payload(
        self, api_client: BackupAPIClient, mock_session: AsyncMock
    ) -> None:
        """Запрос с JSON payload корректно передаётся."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"status": "success"})
        mock_response.__aenter__.return_value = mock_response
        mock_response.__aexit__.return_value = None

        mock_session.request.return_value = mock_response

        payload = {"dry_run": True, "reason": "manual"}
        await api_client.request("POST", "/api/backups/test/backup", json=payload)

        call_kwargs = mock_session.request.call_args[1]
        assert call_kwargs["json"] == payload

    @pytest.mark.asyncio
    async def test_request_4xx_raises_immediately(
        self, api_client: BackupAPIClient, mock_session: AsyncMock
    ) -> None:
        """4xx код → немедленный raise APIClientError (без ретраев)."""
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.text = AsyncMock(return_value='{"detail": "Not found"}')
        mock_response.__aenter__.return_value = mock_response
        mock_response.__aexit__.return_value = None

        mock_session.request.return_value = mock_response

        with pytest.raises(APIClientError) as exc_info:
            await api_client.request("GET", "/api/backups/nonexistent")

        assert exc_info.value.status_code == 404
        assert "404" in str(exc_info.value)
        # Проверяем что был только один вызов (без ретраев)
        assert mock_session.request.call_count == 1

    @pytest.mark.asyncio
    async def test_request_5xx_retries_3_times(
        self, api_client: BackupAPIClient, mock_session: AsyncMock
    ) -> None:
        """5xx код → 3 попытки с backoff."""
        mock_response = AsyncMock()
        mock_response.status = 503
        mock_response.text = AsyncMock(return_value="Service Unavailable")
        mock_response.__aenter__.return_value = mock_response
        mock_response.__aexit__.return_value = None

        mock_session.request.return_value = mock_response

        with pytest.raises(APIClientError) as exc_info:
            await api_client.request("GET", "/api/backups/test")

        assert exc_info.value.status_code == 503
        # Проверяем что было 3 попытки (max_retries по умолчанию)
        assert mock_session.request.call_count == 3

    @pytest.mark.asyncio
    async def test_request_timeout_retry(
        self, api_client: BackupAPIClient, mock_session: AsyncMock
    ) -> None:
        """TimeoutError → ретрай."""
        mock_session.request.side_effect = asyncio.TimeoutError("Connection timeout")

        with pytest.raises(APIClientError) as exc_info:
            await api_client.request("GET", "/api/backups/test")

        assert "timeout" in str(exc_info.value).lower() or "TimeoutError" in str(exc_info.value)
        # Проверяем несколько попыток
        assert mock_session.request.call_count > 1

    @pytest.mark.asyncio
    async def test_backup_create_success(
        self, api_client: BackupAPIClient, mock_session: AsyncMock, backup_response_success: Dict[str, Any]
    ) -> None:
        """Создание бэкапа возвращает BackupResponse."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=backup_response_success)
        mock_response.__aenter__.return_value = mock_response
        mock_response.__aexit__.return_value = None

        mock_session.request.return_value = mock_response

        result = await api_client.create_backup("test-service", dry_run=False)

        assert isinstance(result, BackupResponse)
        assert result.snapshot_id == "k123456789"
        assert result.status == "success"
        assert not result.dry_run

        mock_session.request.assert_called_once_with(
            "POST",
            "http://localhost:8000/api/backups/test-service/backup",
            headers={"Authorization": "Bearer test-key"},
            json={"dry_run": False},
            timeout=ClientTimeout(total=30),
        )

    @pytest.mark.asyncio
    async def test_backup_create_dry_run(
        self, api_client: BackupAPIClient, mock_session: AsyncMock, backup_response_dry_run: Dict[str, Any]
    ) -> None:
        """Создание бэкапа в dry_run режиме."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=backup_response_dry_run)
        mock_response.__aenter__.return_value = mock_response
        mock_response.__aexit__.return_value = None

        mock_session.request.return_value = mock_response

        result = await api_client.create_backup("test-service", dry_run=True)

        assert isinstance(result, BackupResponse)
        assert result.snapshot_id is None
        assert result.status == "dry_run"
        assert result.dry_run

        mock_session.request.assert_called_once_with(
            "POST",
            "http://localhost:8000/api/backups/test-service/backup",
            headers={"Authorization": "Bearer test-key"},
            json={"dry_run": True},
            timeout=ClientTimeout(total=30),
        )

    @pytest.mark.asyncio
    async def test_backup_create_disabled(
        self, api_client: BackupAPIClient, mock_session: AsyncMock, backup_response_disabled: Dict[str, Any]
    ) -> None:
        """Создание бэкапа, когда бэкап отключён."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=backup_response_disabled)
        mock_response.__aenter__.return_value = mock_response
        mock_response.__aexit__.return_value = None

        mock_session.request.return_value = mock_response

        result = await api_client.create_backup("test-service")

        assert isinstance(result, BackupResponse)
        assert result.snapshot_id is None
        assert result.status == "disabled"
        assert not result.dry_run

    @pytest.mark.asyncio
    async def test_list_backups_success(
        self, api_client: BackupAPIClient, mock_session: AsyncMock
    ) -> None:
        """Получение списка снапшотов."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[
            {"snapshot_id": "k123456789", "created_at": "2024-01-01T12:00:00Z", "size_bytes": 1024 * 1024},
            {"snapshot_id": "k987654321", "created_at": "2024-01-02T12:00:00Z", "size_bytes": 2048 * 1024},
        ])
        mock_response.__aenter__.return_value = mock_response
        mock_response.__aexit__.return_value = None

        mock_session.request.return_value = mock_response

        result = await api_client.list_backups("test-service")

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["snapshot_id"] == "k123456789"
        assert result[1]["snapshot_id"] == "k987654321"

        mock_session.request.assert_called_once_with(
            "GET",
            "http://localhost:8000/api/backups/test-service",
            headers={"Authorization": "Bearer test-key"},
            timeout=ClientTimeout(total=30),
        )

    @pytest.mark.asyncio
    async def test_list_backups_empty(
        self, api_client: BackupAPIClient, mock_session: AsyncMock
    ) -> None:
        """Получение пустого списка снапшотов."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[])
        mock_response.__aenter__.return_value = mock_response
        mock_response.__aexit__.return_value = None

        mock_session.request.return_value = mock_response

        result = await api_client.list_backups("test-service")

        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_restore_backup_with_force(
        self, api_client: BackupAPIClient, mock_session: AsyncMock
    ) -> None:
        """Восстановление снапшота с force=true."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True, "message": "Restoration started"})
        mock_response.__aenter__.return_value = mock_response
        mock_response.__aexit__.return_value = None

        mock_session.request.return_value = mock_response

        result = await api_client.restore_backup("test-service", "k123456789", force=True)

        assert result == {"success": True, "message": "Restoration started"}

        mock_session.request.assert_called_once_with(
            "POST",
            "http://localhost:8000/api/backups/test-service/restore/k123456789",
            headers={"Authorization": "Bearer test-key"},
            json={"force": True},
            timeout=ClientTimeout(total=30),
        )

    @pytest.mark.asyncio
    async def test_delete_backup_success(
        self, api_client: BackupAPIClient, mock_session: AsyncMock
    ) -> None:
        """Удаление снапшота."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True, "message": "Snapshot deleted"})
        mock_response.__aenter__.return_value = mock_response
        mock_response.__aexit__.return_value = None
        mock_response.text = AsyncMock(return_value="")

        mock_session.request.return_value = mock_response

        result = await api_client.delete_backup("k123456789")

        assert result == {"success": True, "message": "Snapshot deleted"}

        mock_session.request.assert_called_once_with(
            "DELETE",
            "http://localhost:8000/api/backups/snapshot/k123456789",
            headers={"Authorization": "Bearer test-key"},
            timeout=ClientTimeout(total=30),
        )

    @pytest.mark.asyncio
    async def test_delete_backup_204_no_content(
        self, api_client: BackupAPIClient, mock_session: AsyncMock
    ) -> None:
        """Удаление снапшота с 204 No Content."""
        mock_response = AsyncMock()
        mock_response.status = 204
        mock_response.text = AsyncMock(return_value="")
        mock_response.__aenter__.return_value = mock_response
        mock_response.__aexit__.return_value = None

        mock_session.request.return_value = mock_response

        result = await api_client.delete_backup("k123456789")

        assert result == {"success": True, "message": "Snapshot deleted (204 No Content)"}