"""
Асинхронный HTTP клиент для взаимодействия с Platform Master Service API.
Поддерживает Bearer token аутентификацию, retry логику и обработку ошибок.
"""

import asyncio
import logging
import os
from typing import Any
from typing import Any

import aiohttp
from aiohttp import ClientSession, ClientTimeout
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# Константы
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_WAIT_MIN = 1
RETRY_WAIT_MAX = 10


def _retry_error_callback(retry_state):
    """
    Callback для преобразования RetryError в APIClientError.
    """
    # retry_state.outcome содержит результат последней попытки (исключение)
    if retry_state.outcome is None:
        raise APIClientError("Unknown error after retries")
    exception = retry_state.outcome.exception()
    if exception is None:
        raise APIClientError("Unknown error after retries")
    # Если исключение уже APIClientError, просто поднимаем его
    if isinstance(exception, APIClientError):
        raise exception
    # Преобразуем в APIClientError с сообщением исходного исключения
    raise APIClientError(f"{type(exception).__name__}: {exception}") from exception


class APIClientError(Exception):
    """Базовое исключение для ошибок API клиента."""


class APIClient:
    """HTTP клиент для Platform Master Service API."""

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        api_key: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        verify_ssl: bool = True,
    ) -> None:
        """
        Инициализация API клиента.

        Args:
            base_url: Базовый URL API
            token: Bearer token для авторизации
            api_key: Bearer token (алиас для token, для обратной совместимости)
            timeout: Таймаут запросов в секундах
            verify_ssl: Проверять ли SSL сертификат
        """
        self.base_url = base_url.rstrip("/")
        self.token = token or api_key
        self.timeout = ClientTimeout(total=timeout)
        self.verify_ssl = verify_ssl
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "APIClient":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def start(self) -> None:
        """Создание сессии aiohttp."""
        if self._session is None or self._session.closed:
            headers = {"User-Agent": "Platform-CLI/1.0"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            self._session = ClientSession(
                headers=headers,
                timeout=self.timeout,
                connector=aiohttp.TCPConnector(ssl=self.verify_ssl),
            )

    async def close(self) -> None:
        """Закрытие сессии aiohttp."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Выполнение HTTP запроса (без ретраев).

        Ретраи включаются только для идемпотентных методов (GET, DELETE, HEAD)
        через :meth:`_request_idempotent`. Для state-mutating POST/PUT/PATCH
        ретраи отключены: при сетевом сбое после обработки запроса сервером
        повторный вызов привёл бы к дублированию операции (см. backup create,
        restore).
        """
        if self._session is None or self._session.closed:
            await self.start()

        url = f"{self.base_url}{endpoint}"
        logger.debug(f"API request: {method} {url}")

        try:
            async with self._session.request(
                method=method,
                url=url,
                json=json_data,
                params=params,
                ssl=None if self.verify_ssl else False,
            ) as response:
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    return await response.json()
                else:
                    text = await response.text()
                    return {"text": text}
        except aiohttp.ClientResponseError as e:
            logger.error(f"API error {e.status}: {e.message}")
            raise APIClientError(f"API error {e.status}: {e.message}") from e

    @retry(
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(min=RETRY_WAIT_MIN, max=RETRY_WAIT_MAX),
        retry_error_callback=lambda retry_state: _retry_error_callback(retry_state),
    )
    async def _request_idempotent(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Идемпотентный запрос с ретраями (GET, DELETE, HEAD)."""
        return await self._request(method, endpoint, params=params)

    async def post(self, endpoint: str, json_data: dict[str, Any] | None = None) -> dict[str, Any]:
        """POST запрос. Ретраи отключены (non-idempotent)."""
        return await self._request("POST", endpoint, json_data=json_data)

    async def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET запрос. Ретраи включены (идемпотентный)."""
        return await self._request_idempotent("GET", endpoint, params=params)

    async def delete(self, endpoint: str) -> dict[str, Any]:
        """DELETE запрос. Ретраи включены (идемпотентный)."""
        return await self._request_idempotent("DELETE", endpoint)

    # Специфичные методы для backup API

    async def create_backup(self, service_name: str) -> dict[str, Any]:
        """
        Создать бэкап сервиса.

        Args:
            service_name: Имя сервиса

        Returns:
            Ответ API с результатом операции
        """
        endpoint = f"/api/backups/{service_name}/backup"
        return await self.post(endpoint)

    async def list_backups(self, service_name: str) -> list[dict[str, Any]]:
        """
        Получить список снапшотов сервиса.

        Args:
            service_name: Имя сервиса

        Returns:
            Список снапшотов
        """
        endpoint = f"/api/backups/{service_name}"
        response = await self.get(endpoint)
        # API возвращает список объектов BackupSnapshotResponse
        return response if isinstance(response, list) else []

    async def restore_backup(
        self,
        service_name: str,
        snapshot_id: str,
        target: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Восстановить снапшот сервиса.

        Args:
            service_name: Имя сервиса
            snapshot_id: ID снапшота
            target: Целевой путь (опционально)
            force: Принудительное восстановление (опционально)

        Returns:
            Ответ API с результатом операции
        """
        endpoint = f"/api/backups/{service_name}/restore/{snapshot_id}"
        json_data = {}
        if target is not None:
            json_data["target"] = target
        if force:
            json_data["force"] = force
        return await self.post(endpoint, json_data=json_data)

    async def delete_backup(self, snapshot_id: str) -> dict[str, Any]:
        """
        Удалить снапшот.

        Args:
            snapshot_id: ID снапшота

        Returns:
            Ответ API с результатом операции
        """
        endpoint = f"/api/backups/snapshot/{snapshot_id}"
        return await self.delete(endpoint)


def get_api_client() -> APIClient:
    """
    Создание экземпляра APIClient на основе конфигурации.

    Returns:
        Настроенный экземпляр APIClient
    """
    from .config import get_config, _get_ssl_verify
    from .cli import _get_ssl_verify, get_config

    config = get_config()
    master_url = config.get("master_url", "http://localhost:8001")
    token = os.getenv("PLATFORM_API_TOKEN")
    insecure = os.getenv("PLATFORM_INSECURE", "").lower() == "true"
    verify_ssl = _get_ssl_verify(insecure=insecure)

    return APIClient(
        base_url=master_url,
        token=token,
        verify_ssl=verify_ssl,
    )
