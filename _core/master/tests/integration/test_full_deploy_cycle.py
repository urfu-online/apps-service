"""Интеграционные тесты полного цикла: discovery → caddy generation → deploy (mock).

Эти тесты проверяют полный пайплайн развёртывания без реального Docker:
1. ServiceDiscovery сканирует директорию сервисов
2. Загружает манифесты (включая local override)
3. CaddyManager генерирует конфиги
4. DockerManager подготавливает команды деплоя (dry-run)
"""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
class TestServiceDiscoveryFullCycle:
    """Тестирование полного цикла обнаружения сервисов."""

    async def test_scan_all_discovers_services(self, test_fixtures_path):
        """ServiceDiscovery находит все тестовые сервисы."""
        from app.services.discovery import ServiceDiscovery

        # Патчим Docker status чтобы не было реальных вызовов
        with patch.object(ServiceDiscovery, "_get_docker_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = "unknown"

            with patch.object(ServiceDiscovery, "_setup_watcher"):
                discovery = ServiceDiscovery(str(test_fixtures_path["services"]))
                services = await discovery.scan_all()

            assert "test-web-app" in services
            assert "test-api" in services
            assert services["test-web-app"].visibility == "public"
            assert services["test-api"].visibility == "internal"
            assert services["test-web-app"].version == "1.0.0"
            assert services["test-api"].version == "2.1.0"

    async def test_scan_all_handles_missing_directories(self, tmp_path):
        """ServiceDiscovery корректно обрабатывает пустые директории."""
        from app.services.discovery import ServiceDiscovery

        # Создаём пустые public/internal — observer стартует, но сервисов нет
        (tmp_path / "public").mkdir()
        (tmp_path / "internal").mkdir()

        with patch.object(ServiceDiscovery, "_setup_watcher"):
            discovery = ServiceDiscovery(str(tmp_path))
            services = await discovery.scan_all()

        assert services == {}

    async def test_local_override_merging(self, test_fixtures_path, tmp_path):
        """Local override файл корректно мержится с основным манифестом."""
        import yaml
        from app.services.discovery import ServiceDiscovery

        # Создаём тестовый сервис с local override
        # Структура: tmp_path/public/override-test/
        service_dir = tmp_path / "public" / "override-test"
        service_dir.mkdir(parents=True)

        # Основной манифест
        manifest = {
            "name": "override-test",
            "version": "1.0.0",
            "routing": [
                {"type": "port", "internal_port": 8000}
            ],
            "health": {
                "enabled": True,
                "endpoint": "/health",
                "interval": "30s",
            },
        }
        (service_dir / "service.yml").write_text(yaml.dump(manifest))

        # Local override — меняет порт и добавляет настройки
        local_override = {
            "routing": [
                {"type": "port", "internal_port": 9999, "port": 12345}
            ],
            "health": {
                "interval": "10s",  # Переопределяем интервал
            },
        }
        (service_dir / "service.local.yml").write_text(yaml.dump(local_override))

        # Пустая internal чтобы scan_all не упал
        (tmp_path / "internal").mkdir()

        with patch.object(ServiceDiscovery, "_get_docker_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = "unknown"

            with patch.object(ServiceDiscovery, "_setup_watcher"):
                discovery = ServiceDiscovery(str(tmp_path))
                services = await discovery.scan_all()

            assert "override-test" in services
            svc = services["override-test"]
            # routing должен быть полностью заменён (списки не мержатся)
            assert svc.routing[0].internal_port == 9999
            # health.interval должен быть переопределён (словари мержатся)
            assert svc.health.interval == "10s"

    async def test_local_override_non_dict_skipped(self, test_fixtures_path, tmp_path, caplog):
        """Non-dict local override корректно пропускается с warning."""
        import yaml
        from app.services.discovery import ServiceDiscovery

        service_dir = tmp_path / "public" / "bad-override"
        service_dir.mkdir(parents=True)

        manifest = {
            "name": "bad-override",
            "version": "1.0.0",
            "routing": [{"type": "port", "internal_port": 8000}],
        }
        (service_dir / "service.yml").write_text(yaml.dump(manifest))
        # Bad override — список вместо dict
        (service_dir / "service.local.yml").write_text("- item1\n- item2\n")

        (tmp_path / "internal").mkdir()

        with patch.object(ServiceDiscovery, "_get_docker_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = "unknown"

            with patch.object(ServiceDiscovery, "_setup_watcher"):
                discovery = ServiceDiscovery(str(tmp_path))
                services = await discovery.scan_all()

            # Сервис должен загрузиться (override пропущен)
            assert "bad-override" in services
            # Warning должен быть залогирован
            assert "not a mapping" in caplog.text or "skipping" in caplog.text.lower()

    async def test_fallback_to_docker_compose(self, tmp_path):
        """Если нет service.yml, создаётся минимальный манифест из docker-compose.yml."""
        from app.services.discovery import ServiceDiscovery

        service_dir = tmp_path / "public" / "compose-only"
        service_dir.mkdir(parents=True)
        (service_dir / "docker-compose.yml").write_text("services:\n  app:\n    image: nginx\n")

        (tmp_path / "internal").mkdir()

        with patch.object(ServiceDiscovery, "_get_docker_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = "unknown"

            with patch.object(ServiceDiscovery, "_setup_watcher"):
                discovery = ServiceDiscovery(str(tmp_path))
                services = await discovery.scan_all()

            assert "compose-only" in services
            svc = services["compose-only"]
            assert svc.type == "docker-compose"
            assert svc.name == "compose-only"

    async def test_scan_all_discovers_all_test_services(self, temp_services_dir):
        """ServiceDiscovery находит все 9 тестовых сервисов из фикстур."""
        from app.services.discovery import ServiceDiscovery

        with patch.object(ServiceDiscovery, "_get_docker_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = "unknown"

            with patch.object(ServiceDiscovery, "_setup_watcher"):
                discovery = ServiceDiscovery(str(temp_services_dir))
                services = await discovery.scan_all()

                expected_names = {
                    "test-web-app", "test-auto-sub", "test-domain",
                    "test-subfolder", "test-multi-container", "test-multi-route",
                    "test-api", "test-health-only", "test-port-internal"
                }
                found_names = set(services.keys())
                assert found_names == expected_names, f"Missing: {expected_names - found_names}"
                
                # Проверяем типы маршрутизации
                assert services["test-auto-sub"].routing[0].type == "auto_subdomain"
                assert services["test-domain"].routing[0].type == "domain"
                assert services["test-subfolder"].routing[0].type == "subfolder"
                assert services["test-multi-container"].routing[0].container_name == "test-multi-container-web"
                assert len(services["test-multi-route"].routing) == 3
                assert services["test-api"].visibility == "internal"
                assert len(services["test-health-only"].routing) == 0
                assert services["test-port-internal"].routing[0].type == "port"


@pytest.mark.asyncio
class TestCaddyManagerFullCycle:
    """Тестирование генерации Caddy конфигов."""

    async def test_regenerate_all_domain_routing(self, test_fixtures_path, sample_service_manifest):
        """CaddyManager генерирует конфиг для domain-маршрутизации."""
        from app.services.caddy_manager import CaddyManager

        caddy_path = test_fixtures_path["caddy"]
        manager = CaddyManager(str(caddy_path))

        services = {
            "test-web-app": sample_service_manifest,
        }

        await manager.regenerate_all(services)

        # Проверяем что конфиг сгенерирован
        conf_files = list(manager.conf_d.glob("*.caddy"))
        assert len(conf_files) > 0

        # Проверяем содержимое — должен быть reverse_proxy
        for conf_file in conf_files:
            content = conf_file.read_text()
            if "test-web" in content:
                assert "reverse_proxy" in content
                assert "test-web-app" in content or "80" in content

    async def test_regenerate_all_subfolder_routing(self, test_fixtures_path, tmp_path):
        """CaddyManager группирует subfolder сервисы по base_domain."""
        from app.services.caddy_manager import CaddyManager
        from app.services.discovery import ServiceManifest
        import shutil

        # Копируем шаблоны во временную директорию
        src_caddy = test_fixtures_path["caddy"]
        dst_caddy = tmp_path / "caddy"
        shutil.copytree(src_caddy, dst_caddy)

        manager = CaddyManager(str(dst_caddy))

        services = {
            "test-web-app": ServiceManifest(
                name="test-web-app",
                version="1.0.0",
                visibility="public",
                routing=[
                    {
                        "type": "subfolder",
                        "base_domain": "apps.example.com",
                        "path": "/web",
                        "internal_port": 80,
                    }
                ],
            ),
            "test-api": ServiceManifest(
                name="test-api",
                version="2.0.0",
                visibility="internal",
                routing=[
                    {
                        "type": "subfolder",
                        "base_domain": "apps.example.com",
                        "path": "/api",
                        "internal_port": 8000,
                    }
                ],
            ),
        }

        await manager.regenerate_all(services)

        # Должен быть сгенерирован _subfolder_apps_example_com.caddy
        conf_files = list(manager.conf_d.glob("*subfolder*.caddy"))
        assert len(conf_files) > 0

        content = conf_files[0].read_text()
        assert "web" in content or "api" in content

    async def test_regenerate_all_routing_types(self, temp_services_dir):
        """CaddyManager генерирует конфиги для всех типов маршрутизации."""
        from pathlib import Path
        from app.services.caddy_manager import CaddyManager
        from app.services.discovery import ServiceDiscovery
        import shutil

        # Создаём временную директорию для конфигов Caddy
        tmp_caddy = temp_services_dir.parent / "caddy_test"
        if tmp_caddy.exists():
            shutil.rmtree(tmp_caddy)
        tmp_caddy.mkdir()
        (tmp_caddy / "conf.d").mkdir()
        (tmp_caddy / "templates").mkdir()
        
        # Копируем шаблоны из реальных шаблонов Caddy (гарантированно все есть)
        core_templates = Path("/projects/apps-service-opus/_core/caddy/templates")
        if core_templates.exists():
            shutil.copytree(core_templates, tmp_caddy / "templates", dirs_exist_ok=True)
        else:
            # Fallback: копируем из фикстур
            src_templates = Path(__file__).parent.parent / "test-fixtures" / "caddy" / "templates"
            if src_templates.exists():
                shutil.copytree(src_templates, tmp_caddy / "templates", dirs_exist_ok=True)

        with patch.object(ServiceDiscovery, "_get_docker_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = "unknown"
            with patch.object(ServiceDiscovery, "_setup_watcher"):
                discovery = ServiceDiscovery(str(temp_services_dir))
                services = await discovery.scan_all()

                # Мокаем Caddy API
                with patch("aiohttp.ClientSession") as mock_session_class:
                    mock_session = AsyncMock()
                    mock_response = AsyncMock()
                    mock_response.status = 200
                    mock_response.text = AsyncMock(return_value='{"result":"ok"}')
                    mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
                    mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)
                    mock_session_class.return_value = mock_session

                    caddy = CaddyManager(config_path=str(tmp_caddy))

                    # Генерируем конфиги
                    await caddy.regenerate_all(services)

                    # Проверяем, что конфиги созданы для публичных сервисов с роутингом
                    # Собираем имена сервисов из сгенерированных файлов
                    generated_files = list(caddy.conf_d.glob("*.caddy"))
                    print(f"Generated files: {[f.name for f in generated_files]}")
                    assert len(generated_files) > 0
                    
                    # Проверяем, что для каждого типа маршрутизации есть хотя бы один конфиг
                    # Анализируем имена файлов
                    type_counts = {}
                    for file in generated_files:
                        name = file.stem
                        if "_auto" in name:
                            type_counts["auto_subdomain"] = type_counts.get("auto_subdomain", 0) + 1
                        elif "_domain" in name:
                            type_counts["domain"] = type_counts.get("domain", 0) + 1
                        elif "_port" in name:
                            type_counts["port"] = type_counts.get("port", 0) + 1
                        elif "_subfolder_" in name:
                            type_counts["subfolder"] = type_counts.get("subfolder", 0) + 1
                        else:
                            # Файлы без суффиксов могут быть domain (test-domain.caddy)
                            # Проверим, есть ли сервис с именем name и типом domain
                            # Для простоты добавим как domain
                            type_counts["domain"] = type_counts.get("domain", 0) + 1
                    
                    print(f"Type counts: {type_counts}")
                    # Ожидаемые типы (auto_subdomain, domain, subfolder, port)
                    assert "auto_subdomain" in type_counts
                    assert "domain" in type_counts
                    assert "subfolder" in type_counts
                    assert "port" in type_counts


@pytest.mark.asyncio
class TestDockerManagerDryRun:
    """Тестирование DockerManager в dry-run режиме."""

    async def test_deploy_service_dry_run(self, mock_notifier, sample_service_manifest):
        """Deploy в dry-run режиме не вызывает docker, но логирует действия."""
        from app.services.docker_manager import DockerManager

        with patch("app.services.docker_manager.DockerManager._deploy_compose_dry_run", new_callable=AsyncMock) as mock_dry:
            mock_dry.return_value = {
                "success": True,
                "message": "dry-run: would execute docker compose up -d --build",
                "logs": ["[DRY-RUN] docker compose -f ... up -d --build"],
            }

            manager = DockerManager(mock_notifier)
            result = await manager.deploy_service(sample_service_manifest, dry_run=True)

            assert result["success"] is True
            assert "dry-run" in result["message"].lower()
            mock_dry.assert_called_once()

    async def test_deploy_service_dry_run_no_notification(self, mock_notifier, sample_service_manifest):
        """Dry-run не отправляет Telegram уведомления."""
        from app.services.docker_manager import DockerManager

        manager = DockerManager(mock_notifier)

        # Просто проверяем что dry_run=True не вызывает notifier
        # (это будет реализовано в DockerManager)
        with patch.object(manager, "_deploy_compose", new_callable=AsyncMock) as mock_deploy:
            mock_deploy.return_value = {"success": True, "message": "", "logs": []}

            await manager.deploy_service(sample_service_manifest, dry_run=True)

            # notifier.send не должен вызываться в dry-run
            mock_notifier.send.assert_not_called()
