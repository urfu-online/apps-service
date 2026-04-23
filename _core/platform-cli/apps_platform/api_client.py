"""
Асинхронный HTTP клиент для взаимодействия с Platform Master Service API.
Поддерживает Bearer token аутентификацию, retry логику и обработку ошибок.
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import aiohttp
from aiohttp import ClientSession, ClientTimeout
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    retry_error_callback,
    RetryError,
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

    pass


class APIClient:
    """HTTP клиент для Platform Master Service API."""

    def __init__(
        self,
        base_url: str,
        token: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        verify_ssl: bool = True,
    ) -> None:
        """
        Инициализация клиента.

        Args:
            base_url: Базовый URL API (например, http://localhost:8001)
            token: Bearer token для аутентификации (опционально)
            timeout: Таймаут запроса в секундах
            verify_ssl: Проверять SSL сертификаты
        """
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = ClientTimeout(total=timeout)
        self.verify_ssl = verify_ssl
        self._session: Optional[ClientSession] = None

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

    @retry(
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(min=RETRY_WAIT_MIN, max=RETRY_WAIT_MAX),
        retry_error_callback=lambda retry_state: _retry_error_callback(retry_state),
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Выполнение HTTP запроса с retry логикой."""
        if self._session is None or self._session.closed:
            await self.start()

        url = f"{self.base_url}{endpoint}"
        logger.debug(f"API request: {method} {url}")

        try:
            async with self._session.request(
                method=method,
                url=url,
                json=json,
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

    async def post(self, endpoint: str, json: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """POST запрос."""
        return await self._request("POST", endpoint, json=json)

    async def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """GET запрос."""
        return await self._request("GET", endpoint, params=params)

    async def delete(self, endpoint: str) -> Dict[str, Any]:
        """DELETE запрос."""
        return await self._request("DELETE", endpoint)

    # Специфичные методы для backup API

    async def create_backup(self, service_name: str) -> Dict[str, Any]:
        """
        Создать бэкап сервиса.

        Args:
            service_name: Имя сервиса

        Returns:
            Ответ API с результатом операции
        """
        endpoint = f"/api/backups/{service_name}/backup"
        return await self.post(endpoint)

    async def list_backups(self, service_name: str) -> List[Dict[str, Any]]:
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
        target: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
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
        json = {}
        if target is not None:
            json["target"] = target
        if force:
            json["force"] = force
        return await self.post(endpoint, json=json)

    async def delete_backup(self, snapshot_id: str) -> Dict[str, Any]:
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
    from .cli import get_config, _get_ssl_verify

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