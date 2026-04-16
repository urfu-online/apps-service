"""Тесты для endpoints TLS - Pydantic модели."""
import pytest


class TestTLSModels:
    """Тесты Pydantic моделей для TLS."""

    def test_tls_validation_response(self):
        """Тест модели TLSValidationResponse."""
        from app.api.routes.tls import TLSValidationResponse
        
        response = TLSValidationResponse(
            status="ok",
            service="test-service",
            domain="test.example.com"
        )
        
        assert response.status == "ok"
        assert response.service == "test-service"
        assert response.domain == "test.example.com"

    def test_tls_validation_response_without_service(self):
        """Тест модели TLSValidationResponse без service."""
        from app.api.routes.tls import TLSValidationResponse
        
        response = TLSValidationResponse(
            status="ok",
            domain="test.example.com"
        )
        
        assert response.status == "ok"
        assert response.service is None
        assert response.domain == "test.example.com"
