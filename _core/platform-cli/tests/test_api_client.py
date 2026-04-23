"""Тесты для API клиента."""
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
import aiohttp

from apps_platform.api_client import APIClient, APIClientError


class TestAPIClient:
    """Тесты APIClient."""

    @pytest.fixture
    def client(self):
        """Экземпляр APIClient для тестов."""
        return APIClient(base_url="http://localhost:8001", token="test-token")

    @pytest.mark.asyncio
    async def test_start_and_close(self, client):
        """Создание и закрытие сессии."""
        await client.start()
        assert client._session is not None
        assert not client._session.closed
        await client.close()
        assert client._session is None

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Использование контекстного менеджера."""
        async with APIClient(base_url="http://localhost:8001") as client:
            assert client._session is not None
            assert not client._session.closed
        assert client._session is None

    @pytest.mark.asyncio
    async def test_request_success(self, client):
        """Успешный HTTP запрос."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = MagicMock()
        mock_response.headers.get.return_value = "application/json"
        mock_response.json.return_value = {"success": True}
        mock_response.text.return_value = '{"success": true}'
        # Настраиваем асинхронный контекстный менеджер
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession.request", return_value=mock_response):
            await client.start()
            result = await client._request("GET", "/test")
            assert result == {"success": True}

    @pytest.mark.asyncio
    async def test_request_text_response(self, client):
        """Ответ с текстовым содержимым."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = MagicMock()
        mock_response.headers.get.return_value = "text/plain"
        mock_response.text.return_value = "OK"
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession.request", return_value=mock_response):
            await client.start()
            result = await client._request("GET", "/test")
            assert result == {"text": "OK"}

    @pytest.mark.asyncio
    async def test_request_client_error(self, client):
        """Ошибка клиента (4xx)."""
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.headers = MagicMock()
        mock_response.headers.get.return_value = "application/json"
        mock_response.json.return_value = {"detail": "Not found"}
        # raise_for_status должен быть MagicMock, потому что это синхронный метод
        mock_response.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(
                request_info=MagicMock(),
                history=(),
                status=404,
                message="Not found",
            )
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession.request", return_value=mock_response):
            await client.start()
            with pytest.raises(APIClientError, match="API error 404"):
                await client._request("GET", "/test")

    @pytest.mark.asyncio
    async def test_request_network_error(self, client):
        """Сетевая ошибка."""
        with patch("aiohttp.ClientSession.request", side_effect=aiohttp.ClientError("Network error")):
            await client.start()
            with pytest.raises(APIClientError, match="Network error"):
                await client._request("GET", "/test")

    @pytest.mark.asyncio
    async def test_request_timeout(self, client):
        """Таймаут запроса."""
        with patch("aiohttp.ClientSession.request", side_effect=asyncio.TimeoutError("Timeout")):
            await client.start()
            with pytest.raises(APIClientError, match="Request timeout"):
                await client._request("GET", "/test")

    @pytest.mark.asyncio
    async def test_post(self, client):
        """POST запрос."""
        with patch.object(client, "_request", return_value={"id": 1}) as mock_request:
            result = await client.post("/test", json={"key": "value"})
            mock_request.assert_called_once_with("POST", "/test", json={"key": "value"})
            assert result == {"id": 1}

    @pytest.mark.asyncio
    async def test_get(self, client):
        """GET запрос."""
        with patch.object(client, "_request", return_value={"data": "test"}) as mock_request:
            result = await client.get("/test", params={"page": 1})
            mock_request.assert_called_once_with("GET", "/test", params={"page": 1})
            assert result == {"data": "test"}

    @pytest.mark.asyncio
    async def test_delete(self, client):
        """DELETE запрос."""
        with patch.object(client, "_request", return_value={"deleted": True}) as mock_request:
            result = await client.delete("/test")
            mock_request.assert_called_once_with("DELETE", "/test")
            assert result == {"deleted": True}

    @pytest.mark.asyncio
    async def test_create_backup(self, client):
        """Создание бэкапа."""
        with patch.object(client, "post", return_value={"snapshot_id": "k123"}) as mock_post:
            result = await client.create_backup("test-service")
            mock_post.assert_called_once_with("/api/backups/test-service/backup")
            assert result == {"snapshot_id": "k123"}

    @pytest.mark.asyncio
    async def test_list_backups(self, client):
        """Список снапшотов."""
        with patch.object(client, "get", return_value=[{"id": "k123"}]) as mock_get:
            result = await client.list_backups("test-service")
            mock_get.assert_called_once_with("/api/backups/test-service")
            assert result == [{"id": "k123"}]

    @pytest.mark.asyncio
    async def test_restore_backup(self, client):
        """Восстановление снапшота."""
        with patch.object(client, "post", return_value={"operation_id": "op123"}) as mock_post:
            result = await client.restore_backup("test-service", "k123", target="/tmp", force=True)
            mock_post.assert_called_once_with(
                "/api/backups/test-service/restore/k123",
                json={"target": "/tmp", "force": True},
            )
            assert result == {"operation_id": "op123"}

    @pytest.mark.asyncio
    async def test_delete_backup(self, client):
        """Удаление снапшота."""
        with patch.object(client, "delete", return_value={"message": "deleted"}) as mock_delete:
            result = await client.delete_backup("k123")
            mock_delete.assert_called_once_with("/api/backups/snapshot/k123")
            assert result == {"message": "deleted"}

    @pytest.mark.asyncio
    async def test_retry_logic(self, client):
        """Проверка retry логики при сетевых ошибках."""
        # Создаём мок ответа для успешного запроса
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = MagicMock()
        mock_response.headers.get.return_value = "application/json"
        mock_response.json.return_value = {"success": True}
        mock_response.text.return_value = '{"success": true}'
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        # side_effect: два раза исключение, затем успешный ответ
        side_effect = [
            aiohttp.ClientError("Network error"),
            aiohttp.ClientError("Network error"),
            mock_response,
        ]
        with patch("aiohttp.ClientSession.request", side_effect=side_effect):
            await client.start()
            result = await client._request("GET", "/test")
            assert result == {"success": True}
            # Проверяем, что было 3 вызова (два исключения, один успех)
            assert client._session.request.call_count == 3

    def test_get_api_client(self):
        """Создание клиента через get_api_client."""
        with patch("apps_platform.api_client.get_config") as mock_get_config, \
             patch("apps_platform.api_client._get_ssl_verify") as mock_ssl_verify:
            mock_get_config.return_value = {"master_url": "http://master:8001"}
            mock_ssl_verify.return_value = True

            from apps_platform.api_client import get_api_client
            client = get_api_client()
            assert client.base_url == "http://master:8001"
            assert client.token is None
            assert client.verify_ssl is True