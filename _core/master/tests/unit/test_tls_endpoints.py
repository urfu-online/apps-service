"""Tests for TLS validation endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
from app.main import app
from app.services.discovery import ServiceManifest, RoutingConfigModel


class TestTLSValidationEndpoint:
    """Tests for TLS validation endpoint used by Caddy on_demand_tls."""

    @pytest.fixture(autouse=True)
    def setup_app_state(self, mock_discovery):
        """Setup app.state.discovery for each test."""
        app.state.discovery = mock_discovery
        yield
        if hasattr(app.state, 'discovery'):
            delattr(app.state, 'discovery')

    def test_validate_registered_auto_subdomain(self, mock_discovery):
        """Test validation passes for registered auto_subdomain domain."""
        client = TestClient(app)

        response = client.get("/api/tls/validate?domain=test-auto-svc.apps.urfu.online")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "test-auto-svc"
        assert data["domain"] == "test-auto-svc.apps.urfu.online"

    def test_validate_registered_explicit_domain(self, mock_discovery):
        """Test validation passes for explicitly defined domain."""
        client = TestClient(app)

        response = client.get("/api/tls/validate?domain=explicit.example.com")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "explicit-svc"

    def test_validate_unregistered_domain_rejected(self, mock_discovery):
        """Test validation rejects unregistered domain."""
        client = TestClient(app)

        response = client.get("/api/tls/validate?domain=random.apps.urfu.online")

        assert response.status_code == 403
        assert "not registered" in response.json()["detail"]

    def test_validate_empty_domain_rejected(self, mock_discovery):
        """Test validation rejects empty domain."""
        client = TestClient(app)

        response = client.get("/api/tls/validate?domain=")

        assert response.status_code == 403

    def test_validate_random_subdomain_rejected(self, mock_discovery):
        """Test validation rejects random subdomain not in platform."""
        client = TestClient(app)

        # Request for unregistered subdomain
        response = client.get("/api/tls/validate?domain=attacker.apps.urfu.online")

        assert response.status_code == 403


class TestAllowedDomainsEndpoint:
    """Tests for listing allowed domains."""

    @pytest.fixture(autouse=True)
    def setup_app_state(self, mock_discovery):
        """Setup app.state.discovery for each test."""
        app.state.discovery = mock_discovery
        yield
        if hasattr(app.state, 'discovery'):
            delattr(app.state, 'discovery')

    def test_list_allowed_domains(self, mock_discovery):
        """Test listing all allowed domains."""
        client = TestClient(app)

        # Need to mock auth for this endpoint
        with patch('app.core.security.get_current_user') as mock_auth:
            mock_auth.return_value = {"username": "testuser"}

            response = client.get("/api/tls/allowed")

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 2
            assert "test-auto-svc.apps.urfu.online" in data["domains"]
            assert "explicit.example.com" in data["domains"]


class TestDiscoveryDomainValidation:
    """Tests for ServiceDiscovery domain validation methods."""

    def test_validate_domain_auto_subdomain(self, tmp_path):
        """Test validate_domain with auto_subdomain route."""
        from app.services.discovery import ServiceDiscovery, ServiceManifest, RoutingConfigModel

        # Create temp directory for discovery
        services_path = tmp_path / "services"
        services_path.mkdir()

        discovery = ServiceDiscovery(str(services_path))

        # Create mock service with auto_subdomain
        route = RoutingConfigModel(
            type="domain",
            auto_subdomain=True,
            auto_subdomain_base="apps.urfu.online"
        )
        service = ServiceManifest(
            name="my-service",
            routing=[route]
        )
        discovery.services = {"my-service": service}

        # Test valid domain
        is_valid, svc_name = discovery.validate_domain("my-service.apps.urfu.online")
        assert is_valid is True
        assert svc_name == "my-service"

        # Test invalid domain
        is_valid, svc_name = discovery.validate_domain("other-service.apps.urfu.online")
        assert is_valid is False
        assert svc_name is None

        # Cleanup watcher
        discovery.stop_watcher()

    def test_validate_domain_explicit_domain(self, tmp_path):
        """Test validate_domain with explicit domain route."""
        from app.services.discovery import ServiceDiscovery, ServiceManifest, RoutingConfigModel

        services_path = tmp_path / "services"
        services_path.mkdir()

        discovery = ServiceDiscovery(str(services_path))

        route = RoutingConfigModel(
            type="domain",
            domain="custom.urfu.ru",
            auto_subdomain=False
        )
        service = ServiceManifest(
            name="custom-svc",
            routing=[route]
        )
        discovery.services = {"custom-svc": service}

        is_valid, svc_name = discovery.validate_domain("custom.urfu.ru")
        assert is_valid is True
        assert svc_name == "custom-svc"

        is_valid, svc_name = discovery.validate_domain("other.urfu.ru")
        assert is_valid is False

        discovery.stop_watcher()

    def test_get_allowed_domains(self, tmp_path):
        """Test get_allowed_domains returns all registered domains."""
        from app.services.discovery import ServiceDiscovery, ServiceManifest, RoutingConfigModel

        services_path = tmp_path / "services"
        services_path.mkdir()

        discovery = ServiceDiscovery(str(services_path))

        # Service with auto_subdomain
        route1 = RoutingConfigModel(
            type="domain",
            auto_subdomain=True,
            auto_subdomain_base="apps.urfu.online"
        )
        service1 = ServiceManifest(name="svc1", routing=[route1])

        # Service with explicit domain
        route2 = RoutingConfigModel(
            type="domain",
            domain="explicit.example.com",
            auto_subdomain=False
        )
        service2 = ServiceManifest(name="svc2", routing=[route2])

        discovery.services = {"svc1": service1, "svc2": service2}

        allowed = discovery.get_allowed_domains()

        assert "svc1.apps.urfu.online" in allowed
        assert "explicit.example.com" in allowed
        assert len(allowed) == 2

        discovery.stop_watcher()
