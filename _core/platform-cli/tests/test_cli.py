"""
Тесты для CLI модуля apps_platform.cli
"""
import os
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock, mock_open

import pytest
from click.exceptions import Exit
from typer.testing import CliRunner

from apps_platform.caddy_parser import parse_caddy_config

# Импортируем функции для тестирования
from apps_platform.cli import (
    AVAILABILITY_TIMEOUT,
    CADDY_DEFAULT_CONTAINER_NAME,
    DOCKER_TIMEOUT,
    MAX_URLS_DISPLAY,
    REQUEST_TIMEOUT,
    _expand_env_vars,
    _get_ssl_verify,
    _matches_service,
    _parse_caddy_config,
    _parse_compose_port_mapping,
    app,
    validate_service_name,
)

runner = CliRunner()


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

        result = parse_caddy_config("test_service", caddy_path)
        assert result == []

    def test_nonexistent_conf_d(self, tmp_path):
        """Несуществующая директория conf.d возвращает пустой список."""
        caddy_path = tmp_path / "caddy"

        result = parse_caddy_config("test_service", caddy_path)
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

        result = parse_caddy_config("test", caddy_path)
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

        result = parse_caddy_config("test", caddy_path)
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

        result = parse_caddy_config("test", caddy_path)
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

        result = parse_caddy_config("test", caddy_path)
        # Должен быть только example.com, без import
        domains = [r for r in result if r["domain"] != "{"]
        assert len(domains) >= 1

    def test_backward_compat_wrapper(self, tmp_path):
        """Проверяем, что старый импорт `_parse_caddy_config` не сломан."""
        caddy_path = tmp_path / "caddy"
        conf_d = caddy_path / "conf.d"
        conf_d.mkdir(parents=True)

        caddy_file = conf_d / "test.caddy"
        caddy_file.write_text(
            """example.com {
    reverse_proxy http://localhost:8000
}"""
        )

        result = _parse_caddy_config("test", caddy_path)
        assert len(result) == 1


class TestParseComposePortMapping:
    """Тесты парсинга порт-маппинга docker-compose с поддержкой IPv6."""

    @pytest.mark.parametrize(
    "mapping,expected",
    [
            ("8080:80", 8080),
            ("0.0.0.0:8080:80", 8080),
            ("[::1]:8080:80", 8080),
            ("[2001:db8::1]:12345:80", 12345),
            ("8080:80/tcp", 8080),
            ("::1:8080:80", 8080),
    ],
    )
    def test_parse_supported_formats(self, mapping, expected):
        assert _parse_compose_port_mapping(mapping) == expected


class TestValidateServiceName:
    def test_accepts_128_chars(self):
        name = "a" * 128
        assert validate_service_name(name) == name

    def test_rejects_129_chars(self):
        name = "a" * 129
        with pytest.raises(Exit):
            validate_service_name(name)


class TestSslVerifyLogic:
    def test_production_forces_verify_true(self):
        with patch.dict(os.environ, {"PLATFORM_ENV": "production", "PLATFORM_SSL_VERIFY": "false"}, clear=False):
            assert _get_ssl_verify(insecure=False) is True

    def test_production_ignores_insecure_flag(self):
        with patch.dict(os.environ, {"PLATFORM_ENV": "production"}, clear=False):
            assert _get_ssl_verify(insecure=True) is True

    def test_non_production_allows_insecure(self):
        with patch.dict(os.environ, {"PLATFORM_ENV": "development"}, clear=False):
            assert _get_ssl_verify(insecure=True) is False


class TestListAvailabilityIntegration:
    def test_list_check_insecure_ignored_in_production(self):
        with patch.dict(os.environ, {"PLATFORM_ENV": "production"}, clear=False):
            with patch("apps_platform.cli.get_services") as get_services_mock:
                get_services_mock.return_value = {"demo": {"path": Path("/tmp/demo"), "type": "public"}}

                with patch("apps_platform.cli._get_all_container_statuses") as statuses_mock:
                    statuses_mock.return_value = {"demo": "Up 10 seconds"}

                    with patch("apps_platform.cli._get_actual_service_urls") as urls_mock:
                        urls_mock.return_value = ["https://example.com"]

                        with patch("apps_platform.cli.requests.get") as get_mock:
                            get_mock.return_value.status_code = 200

                            result = runner.invoke(app, ["list", "--check", "--insecure"])
                            assert result.exit_code == 0

                            _args, kwargs = get_mock.call_args
                            assert kwargs["verify"] is True

    def test_list_check_insecure_disables_verify_in_dev(self):
        with patch.dict(os.environ, {"PLATFORM_ENV": "development"}, clear=False):
            with patch("apps_platform.cli.get_services") as get_services_mock:
                get_services_mock.return_value = {"demo": {"path": Path("/tmp/demo"), "type": "public"}}

                with patch("apps_platform.cli._get_all_container_statuses") as statuses_mock:
                    statuses_mock.return_value = {"demo": "Up 10 seconds"}

                    with patch("apps_platform.cli._get_actual_service_urls") as urls_mock:
                        urls_mock.return_value = ["https://example.com"]

                        with patch("apps_platform.cli.requests.get") as get_mock:
                            get_mock.return_value.status_code = 200

                            result = runner.invoke(app, ["list", "--check", "--insecure"])
                            assert result.exit_code == 0

                            _args, kwargs = get_mock.call_args
                            assert kwargs["verify"] is False

    @pytest.mark.parametrize(
        "mapping",
        [
            "",  # пусто
            "80",  # только container_port
            "[::1]",  # не похоже на mapping
            "bad:format",
            "127.0.0.1:abc:80",
            "[::1]:abc:80",
            "[::1]:8080",  # нет container_port
        ],
    )
    def test_parse_unsupported_formats(self, mapping):
        assert _parse_compose_port_mapping(mapping) is None


class TestBackupCommands:
    """Тесты команд управления бэкапами Kopia."""

    @pytest.fixture
    def runner(self):
        """CliRunner для тестов."""
        return CliRunner()

    @pytest.fixture
    def mock_backup_api_client(self) -> AsyncMock:
        """Мок BackupAPIClient."""
        client = AsyncMock()
        return client

    @pytest.fixture
    def patch_backup_client(self, mock_backup_api_client: AsyncMock) -> None:
        """Патч для получения BackupAPIClient."""
        with patch("apps_platform.cli.BackupAPIClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_backup_api_client
            yield

    @pytest.fixture
    def mock_service_exists(self) -> None:
        """Мок проверки существования сервиса."""
        with patch("apps_platform.cli._service_exists", return_value=True) as mock:
            yield mock

    @pytest.fixture
    def mock_backup_enabled(self) -> None:
        """Мок проверки включённого бэкапа."""
        with patch("apps_platform.cli._get_backup_enabled", return_value=True) as mock:
            yield mock

    @pytest.fixture
    def mock_backup_disabled(self) -> None:
        """Мок проверки отключённого бэкапа."""
        with patch("apps_platform.cli._get_backup_enabled", return_value=False) as mock:
            yield mock

    @pytest.mark.asyncio
    def test_backup_create_success(
        self,
        runner: CliRunner,
        patch_backup_client: None,
        mock_service_exists: None,
        mock_backup_enabled: None,
        mock_backup_api_client: AsyncMock,
    ) -> None:
        """backup create <svc> → stdout с ✅, код 0."""
        mock_backup_api_client.create_backup.return_value = MagicMock(
            snapshot_id="k123456789",
            status="success",
            message="Backup created successfully",
            dry_run=False,
        )

        result = runner.invoke(app, ["backup", "create", "test-service"])

        assert result.exit_code == 0
        assert "✅" in result.output or "success" in result.output.lower()
        assert "k123456789" in result.output
        mock_backup_api_client.create_backup.assert_called_once_with("test-service", dry_run=False)

    @pytest.mark.asyncio
    def test_backup_create_disabled(
        self,
        runner: CliRunner,
        patch_backup_client: None,
        mock_service_exists: None,
        mock_backup_disabled: None,
    ) -> None:
        """backup create <svc> → stdout с ❌ "disabled", код 1."""
        result = runner.invoke(app, ["backup", "create", "test-service"])

        assert result.exit_code == 1
        assert "disabled" in result.output.lower() or "не включены" in result.output.lower()
        assert "❌" in result.output or "error" in result.output.lower()

    @pytest.mark.asyncio
    def test_backup_create_api_error(
        self,
        runner: CliRunner,
        patch_backup_client: None,
        mock_service_exists: None,
        mock_backup_enabled: None,
        mock_backup_api_client: AsyncMock,
    ) -> None:
        """backup create <svc> → stdout с ❌ "API error", код 1."""
        from platform_cli.api.backup_client import APIClientError
        mock_backup_api_client.create_backup.side_effect = APIClientError("Connection failed", 500)

        result = runner.invoke(app, ["backup", "create", "test-service"])

        assert result.exit_code == 1
        assert "api" in result.output.lower() or "error" in result.output.lower() or "failed" in result.output
        assert "❌" in result.output

    @pytest.mark.asyncio
    def test_backup_list_success(
        self,
        runner: CliRunner,
        patch_backup_client: None,
        mock_service_exists: None,
        mock_backup_api_client: AsyncMock,
    ) -> None:
        """backup list <svc> → таблица Rich/текст с данными, код 0."""
        from datetime import datetime, timezone
        mock_backup_api_client.list_backups.return_value = [
            {
                "snapshot_id": "k123456789",
                "created_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
                "size_bytes": 1024 * 1024,
                "retention_days": 7,
                "status": "completed",
            },
            {
                "snapshot_id": "k987654321",
                "created_at": datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
                "size_bytes": 2048 * 1024,
                "retention_days": 14,
                "status": "completed",
            },
        ]

        result = runner.invoke(app, ["backup", "list", "test-service"])

        assert result.exit_code == 0
        assert "k123456789" in result.output
        assert "k987654321" in result.output
        assert "1.0 MB" in result.output or "1024" in result.output
        mock_backup_api_client.list_backups.assert_called_once_with("test-service")

    @pytest.mark.asyncio
    def test_backup_list_empty(
        self,
        runner: CliRunner,
        patch_backup_client: None,
        mock_service_exists: None,
        mock_backup_api_client: AsyncMock,
    ) -> None:
        """backup list <svc> → "не найдено", код 1."""
        mock_backup_api_client.list_backups.return_value = []

        result = runner.invoke(app, ["backup", "list", "test-service"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "не найдено" in result.output or "empty" in result.output.lower()
        mock_backup_api_client.list_backups.assert_called_once_with("test-service")

    @pytest.mark.asyncio
    def test_backup_list_api_error(
        self,
        runner: CliRunner,
        patch_backup_client: None,
        mock_service_exists: None,
        mock_backup_api_client: AsyncMock,
    ) -> None:
        """backup list <svc> → ошибка API, код 1."""
        from platform_cli.api.backup_client import APIClientError
        mock_backup_api_client.list_backups.side_effect = APIClientError("Service unavailable", 503)

        result = runner.invoke(app, ["backup", "list", "test-service"])

        assert result.exit_code == 1
        assert "api" in result.output.lower() or "error" in result.output.lower() or "503" in result.output
        assert "❌" in result.output

    @pytest.mark.asyncio
    def test_backup_restore_with_force(
        self,
        runner: CliRunner,
        patch_backup_client: None,
        mock_service_exists: None,
        mock_backup_api_client: AsyncMock,
    ) -> None:
        """backup restore <svc> <id> --force → вызов API с force=true, код 0."""
        mock_backup_api_client.restore_backup.return_value = {
            "success": True,
            "message": "Restoration started",
            "operation_id": "restore-op-123",
        }

        result = runner.invoke(
            app,
            ["backup", "restore", "test-service", "k123456789", "--force", "--target", "/tmp/restore"],
        )

        assert result.exit_code == 0
        assert "restoration" in result.output.lower() or "started" in result.output.lower() or "✅" in result.output
        mock_backup_api_client.restore_backup.assert_called_once_with(
            "test-service",
            "k123456789",
            target="/tmp/restore",
            force=True,
        )

    @pytest.mark.asyncio
    def test_backup_restore_without_force(
        self,
        runner: CliRunner,
        patch_backup_client: None,
        mock_service_exists: None,
        mock_backup_api_client: AsyncMock,
    ) -> None:
        """backup restore <svc> <id> (без --force) → вызов API с force=false."""
        mock_backup_api_client.restore_backup.return_value = {
            "success": True,
            "message": "Restoration started",
        }

        result = runner.invoke(
            app,
            ["backup", "restore", "test-service", "k123456789", "--target", "/tmp/restore"],
        )

        assert result.exit_code == 0
        mock_backup_api_client.restore_backup.assert_called_once_with(
            "test-service",
            "k123456789",
            target="/tmp/restore",
            force=False,
        )

    @pytest.mark.asyncio
    def test_backup_delete_success(
        self,
        runner: CliRunner,
        patch_backup_client: None,
        mock_backup_api_client: AsyncMock,
    ) -> None:
        """Удаление снапшота успешно."""
        mock_backup_api_client.delete_backup.return_value = {
            "success": True,
            "message": "Snapshot deleted",
        }

        result = runner.invoke(app, ["backup", "delete", "k123456789"])

        assert result.exit_code == 0
        assert "deleted" in result.output.lower() or "удалён" in result.output or "✅" in result.output
        mock_backup_api_client.delete_backup.assert_called_once_with("k123456789")

    @pytest.mark.asyncio
    def test_backup_delete_not_found(
        self,
        runner: CliRunner,
        patch_backup_client: None,
        mock_backup_api_client: AsyncMock,
    ) -> None:
        """Удаление несуществующего снапшота."""
        from platform_cli.api.backup_client import APIClientError
        mock_backup_api_client.delete_backup.side_effect = APIClientError("Snapshot not found", 404)

        result = runner.invoke(app, ["backup", "delete", "invalid-id"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "404" in result.output or "❌" in result.output
        mock_backup_api_client.delete_backup.assert_called_once_with("invalid-id")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
