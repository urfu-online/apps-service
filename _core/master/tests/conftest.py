"""Фикстуры pytest для тестирования приложения master."""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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
        routing=[{
            "type": "domain",
            "domain": "test-web.example.com",
            "internal_port": 80,
            "container_name": "test-web-app",
        }],
        path=Path("/test/path"),
        status="running",
    )


@pytest.fixture
def mock_discovery():
    """Мокированный ServiceDiscovery для тестов."""
    from app.services.discovery import RoutingConfigModel, ServiceDiscovery, ServiceManifest

    discovery = MagicMock(spec=ServiceDiscovery)

    # Create test services
    route1 = RoutingConfigModel(
        type="domain",
        auto_subdomain=True,
        auto_subdomain_base="apps.urfu.online",
        internal_port=8000,
        container_name="test-auto-svc",
    )
    service1 = ServiceManifest(
        name="test-auto-svc", display_name="Test Auto Service", routing=[route1]
    )

    route2 = RoutingConfigModel(type="domain", domain="explicit.example.com", auto_subdomain=False)
    service2 = ServiceManifest(
        name="explicit-svc", display_name="Explicit Domain Service", routing=[route2]
    )

    discovery.services = {"test-auto-svc": service1, "explicit-svc": service2}

    # Mock validate_domain
    def mock_validate(domain):
        for svc in discovery.services.values():
            for route in svc.routing:
                if route.domain == domain:
                    return (True, svc.name)
                if route.auto_subdomain:
                    expected = f"{svc.name}.{route.auto_subdomain_base}"
                    if domain == expected:
                        return (True, svc.name)
        return (False, None)

    discovery.validate_domain = mock_validate

    # Mock get_allowed_domains
    def mock_allowed():
        allowed = set()
        for svc in discovery.services.values():
            for route in svc.routing:
                if route.domain:
                    allowed.add(route.domain)
                if route.auto_subdomain:
                    allowed.add(f"{svc.name}.{route.auto_subdomain_base}")
        return allowed

    discovery.get_allowed_domains = mock_allowed

    return discovery


@pytest.fixture
def sample_datetime():
    """Образец datetime для тестов."""
    return datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def base_log_entry_response_data(sample_datetime):
    """Базовые данные для тестирования LogEntryResponse."""
    return {
        "timestamp": sample_datetime.isoformat(),
        "level": "info",
        "message": "Test log message",
    }


@pytest.fixture
def base_deployment_response_data(sample_datetime):
    """Базовые данные для тестирования DeploymentResponse."""
    return {
        "id": 1,
        "service_id": 1,
        "version": "1.0.0",
        "status": "completed",
        "started_at": sample_datetime,
        "finished_at": sample_datetime,
        "logs": "Deployment completed successfully",
        "success": True,
        "rollback_available": False,
    }


@pytest.fixture
def base_backup_response_data(sample_datetime):
    """Базовые данные для тестирования BackupResponse."""
    return {
        "id": 1,
        "service_id": 1,
        "filename": "backup_20240101_120000.tar.gz",
        "size": 1024000,
        "timestamp": sample_datetime,
        "status": "completed",
        "type": "full",
        "checksum": "abc123def456",
    }


@pytest.fixture
def base_service_response_data():
    """Базовые данные для тестирования ServiceResponse."""
    return {
        "name": "test-service",
        "display_name": "Test Service",
        "version": "1.0.0",
        "status": "running",
        "visibility": "public",
        "type": "docker-compose",
    }


@pytest.fixture
def base_tls_validation_response_data():
    """Базовые данные для тестирования TLSValidationResponse."""
    return {
        "domain": "example.com",
        "valid": True,
        "expires_at": "2024-12-31T23:59:59Z",
        "issued_by": "Let's Encrypt",
        "certificate_chain": ["cert1", "cert2"],
    }


@pytest.fixture
def mock_service_manifest():
    """Фикстура для создания ServiceManifest."""

    from app.services.discovery import ServiceManifest

    return ServiceManifest(
        name="test-service",
        display_name="Test Service",
        version="1.0.0",
        status="running",
        visibility="public",
        type="docker-compose",
        path=Path("/tmp/test-service"),
    )


@pytest.fixture
def app_with_mock_discovery(mock_discovery):
    """Тестовое приложение с mock discovery."""
    from app.main import app

    # Store original state
    original_discovery = getattr(app.state, "discovery", None)

    # Set mock
    app.state.discovery = mock_discovery

    yield app

    # Restore original state
    if original_discovery:
        app.state.discovery = original_discovery
    elif hasattr(app.state, "discovery"):
        delattr(app.state, "discovery")