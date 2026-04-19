"""
Тесты для CLI модуля apps_platform.cli
"""
import os
import pytest
from unittest.mock import patch

# Импортируем функции для тестирования
from apps_platform.cli import (
    _expand_env_vars,
    _matches_service,
    _parse_caddy_config,
    MAX_URLS_DISPLAY,
    AVAILABILITY_TIMEOUT,
    CADDY_DEFAULT_CONTAINER_NAME,
    DOCKER_TIMEOUT,
    REQUEST_TIMEOUT,
)


class TestConstants:
    """Тесты констант."""

    def test_max_urls_display(self):
        """Проверка константы MAX_URLS_DISPLAY."""
        assert MAX_URLS_DISPLAY == 3

    def test_availability_timeout(self):
        """Проверка константы AVAILABILITY_TIMEOUT."""
        assert AVAILABILITY_TIMEOUT == 3

    def test_caddy_default_container_name(self):
        """Проверка константы CADDY_DEFAULT_CONTAINER_NAME."""
        assert CADDY_DEFAULT_CONTAINER_NAME == "caddy"

    def test_docker_timeout(self):
        """Проверка константы DOCKER_TIMEOUT."""
        assert DOCKER_TIMEOUT == 10

    def test_request_timeout(self):
        """Проверка константы REQUEST_TIMEOUT."""
        assert REQUEST_TIMEOUT == 10


class TestExpandEnvVars:
    """Тесты функции раскрытия переменных окружения."""

    def test_simple_variable(self):
        """Раскрытие простой переменной без значения по умолчанию."""
        with patch.dict(os.environ, {"TEST_VAR": "value"}):
            result = _expand_env_vars("${TEST_VAR}")
            assert result == "value"

    def test_variable_with_default_used(self):
        """Использование значения по умолчанию когда переменная не задана."""
        with patch.dict(os.environ, {}, clear=False):
            # Удаляем переменную если она есть
            env_copy = {k: v for k, v in os.environ.items() if k != "MISSING_VAR"}
            with patch.dict(os.environ, env_copy, clear=True):
                result = _expand_env_vars("${MISSING_VAR:-fallback}")
                assert result == "fallback"

    def test_variable_with_default_not_used(self):
        """Значение по умолчанию не используется когда переменная задана."""
        with patch.dict(os.environ, {"EXISTING_VAR": "actual_value"}):
            result = _expand_env_vars("${EXISTING_VAR:-fallback}")
            assert result == "actual_value"

    def test_no_variables(self):
        """Строка без переменных возвращается как есть."""
        result = _expand_env_vars("plain text without variables")
        assert result == "plain text without variables"

    def test_empty_string(self):
        """Пустая строка возвращается как есть."""
        result = _expand_env_vars("")
        assert result == ""

    def test_multiple_variables(self):
        """Несколько переменных в одной строке."""
        with patch.dict(os.environ, {"VAR1": "first", "VAR2": "second"}):
            result = _expand_env_vars("${VAR1} and ${VAR2}")
            assert result == "first and second"

    def test_mixed_variables_and_defaults(self):
        """Смесь заданных переменных и значений по умолчанию."""
        with patch.dict(os.environ, {"VAR1": "exists"}):
            env_copy = {k: v for k, v in os.environ.items() if k != "VAR2"}
            with patch.dict(os.environ, env_copy, clear=True):
                os.environ["VAR1"] = "exists"
                result = _expand_env_vars("${VAR1} and ${VAR2:-default}")
                assert result == "exists and default"


class TestMatchesService:
    """Тесты функции сопоставления имён контейнеров и сервисов."""

    def test_exact_match(self):
        """Точное совпадение имён."""
        assert _matches_service("caddy", "caddy") is True

    def test_prefix_with_dash(self):
        """Совпадение по префиксу с дефисом."""
        assert _matches_service("caddy-frontend-1", "caddy") is True

    def test_prefix_with_underscore(self):
        """Совпадение по префиксу с подчёркиванием."""
        assert _matches_service("caddy_db_1", "caddy") is True

    def test_suffix_with_dash(self):
        """Совпадение по суффиксу с дефисом."""
        assert _matches_service("platform-caddy", "caddy") is True

    def test_suffix_with_underscore(self):
        """Совпадение по суффиксу с подчёркиванием."""
        assert _matches_service("backup_support_1", "support") is True

    def test_contains_service_name(self):
        """Сервис содержится в имени контейнера."""
        assert _matches_service("course-archive-explorer-backend-1", "course-archive-explorer") is True

    def test_no_match(self):
        """Нет совпадений."""
        assert _matches_service("unrelated-container", "caddy") is False


class TestParseCaddyConfig:
    """Тесты парсинга Caddy конфигурации."""

    def test_empty_conf_d(self, tmp_path):
        """Пустая директория conf.d возвращает пустой список."""
        caddy_path = tmp_path / "caddy"
        conf_d = caddy_path / "conf.d"
        conf_d.mkdir(parents=True)
        
        result = _parse_caddy_config("test_service", caddy_path)
        assert result == []

    def test_nonexistent_conf_d(self, tmp_path):
        """Несуществующая директория conf.d возвращает пустой список."""
        caddy_path = tmp_path / "caddy"
        
        result = _parse_caddy_config("test_service", caddy_path)
        assert result == []

    def test_parse_domain_route(self, tmp_path):
        """Парсинг доменного маршрута."""
        caddy_path = tmp_path / "caddy"
        conf_d = caddy_path / "conf.d"
        conf_d.mkdir(parents=True)
        
        caddy_file = conf_d / "test.caddy"
        caddy_file.write_text("""example.com {
    reverse_proxy http://localhost:8000
}""")
        
        result = _parse_caddy_config("test", caddy_path)
        assert len(result) == 1
        assert result[0]["type"] == "domain"
        assert result[0]["domain"] == "example.com"

    def test_parse_subfolder_route(self, tmp_path):
        """Парсинг маршрута с подпапкой."""
        caddy_path = tmp_path / "caddy"
        conf_d = caddy_path / "conf.d"
        conf_d.mkdir(parents=True)
        
        caddy_file = conf_d / "test.caddy"
        caddy_file.write_text("""example.com {
    handle /api/* {
        reverse_proxy http://localhost:8000
    }
}""")
        
        result = _parse_caddy_config("test", caddy_path)
        # Должен быть домен и subfolder
        domains = [r for r in result if r["type"] == "domain"]
        subfolders = [r for r in result if r["type"] == "subfolder"]
        assert len(domains) >= 1
        assert len(subfolders) >= 1
        assert subfolders[0]["path"] == "/api/*"

    def test_backend_extraction(self, tmp_path):
        """Извлечение бэкэнда из reverse_proxy."""
        caddy_path = tmp_path / "caddy"
        conf_d = caddy_path / "conf.d"
        conf_d.mkdir(parents=True)
        
        caddy_file = conf_d / "test.caddy"
        caddy_file.write_text("""api.example.com {
    reverse_proxy http://backend-service:8080
}""")
        
        result = _parse_caddy_config("test", caddy_path)
        assert len(result) == 1
        assert result[0].get("backend") == "backend-service:8080"

    def test_skip_import_blocks(self, tmp_path):
        """Пропуск блоков import."""
        caddy_path = tmp_path / "caddy"
        conf_d = caddy_path / "conf.d"
        conf_d.mkdir(parents=True)
        
        caddy_file = conf_d / "test.caddy"
        caddy_file.write_text("""import sites/*

example.com {
    reverse_proxy http://localhost:8000
}""")
        
        result = _parse_caddy_config("test", caddy_path)
        # Должен быть только example.com, без import
        domains = [r for r in result if r["domain"] != "{"]
        assert len(domains) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
