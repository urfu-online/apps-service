"""Тесты для моделей - общие проверки дублирующихся Pydantic-моделей."""
import pytest


class TestSharedLogModels:
    """Тесты Pydantic моделей для логов, объединенные из других файлов."""

    def test_log_entry_response(self, base_log_entry_response_data):
        """Тест модели LogEntryResponse."""
        from app.api.routes.logs import LogEntryResponse

        required_fields = {
            "timestamp": base_log_entry_response_data["timestamp"],
            "level": base_log_entry_response_data["level"],
            "message": base_log_entry_response_data["message"]
        }
        
        from .test_model_utils import ModelTestFixture
        model_fixture = ModelTestFixture(LogEntryResponse, required_fields)
        entry = model_fixture.create_instance()
        
        assert model_fixture.validate_required_fields(entry)
        assert entry.timestamp == "2024-01-01T12:00:00+00:00"
        assert entry.level == "info"
        assert entry.message == "Test log message"

    def test_log_search_request(self):
        """Тест модели LogSearchRequest."""
        from app.api.routes.logs import LogSearchRequest

        request = LogSearchRequest(query="error", limit=100)
        assert request.query == "error"
        assert request.limit == 100

    def test_log_search_request_default_limit(self):
        """Тест дефолтного лимита LogSearchRequest."""
        from app.api.routes.logs import LogSearchRequest

        request = LogSearchRequest(query="test")
        assert request.limit == 100
