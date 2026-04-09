"""Фикстуры pytest для тестирования приложения master."""
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# Add app to path for direct pytest runs
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))


@pytest.fixture
def test_fixtures_path():
    """Путь к тестовым фикстурам."""
    base = Path(__file__).parent.parent / "test-fixtures"
    return {
        "services": base / "services",
        "caddy": base / "caddy",
        "backups": base / "backups",
    }


@pytest.fixture
def mock_docker_client():
    """Мокированный Docker клиент."""
    with patch("docker.from_env") as mock_from_env:
        mock_client = MagicMock()
        mock_from_env.return_value = mock_client

        # Mock containers
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.attrs = {
            "State": {"Status": "running"},
            "NetworkSettings": {"Ports": {"80/tcp": [{"HostPort": "9001"}]}},
        }
        mock_container.name = "test-container"

        mock_client.containers.list.return_value = [mock_container]
        mock_client.containers.get.return_value = mock_container

        yield mock_client


@pytest.fixture
def mock_docker_compose():
    """Мокированный docker compose."""
    with patch("app.services.docker_manager.DockerManager._get_compose_command") as mock_compose:
        mock_compose.return_value = ["docker", "compose"]
        yield mock_compose


@pytest.fixture
def mock_notifier():
    """Мокированный Telegram нотификатор."""
    notifier = AsyncMock()
    notifier.send = AsyncMock()
    return notifier


@pytest.fixture
def mock_aiohttp_session():
    """Мокированный aiohttp session для Caddy API."""
    mock_session = AsyncMock()
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value='{"result":"ok"}')
    mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
    mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_session


@pytest.fixture
def sample_service_manifest():
    """Пример ServiceManifest для тестов."""
    from app.services.discovery import ServiceManifest

    return ServiceManifest(
        name="test-web-app",
        display_name="Test Web App",
        version="1.0.0",
        description="Test service",
        type="docker-compose",
        visibility="public",
        routing=[
            {
                "type": "domain",
                "domain": "test-web.example.com",
                "internal_port": 80,
                "container_name": "test-web-app",
            }
        ],
        path=Path("/test/path"),
        status="running",
    )
