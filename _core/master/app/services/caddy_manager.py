from pathlib import Path
from typing import Dict
import aiofiles
import aiohttp
from jinja2 import Environment, FileSystemLoader
from datetime import datetime, timezone
import logging

from app.services.discovery import ServiceManifest
from app.config import settings

# Настройка логирования
logger = logging.getLogger(__name__)


class CaddyManager:
    """Управление конфигурацией Caddy"""
    
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.conf_d = self.config_path / "conf.d"
        self.conf_d.mkdir(parents=True, exist_ok=True)
        
        # Jinja2 для генерации конфигов
        self.jinja = Environment(
            loader=FileSystemLoader(
                str(self.config_path / "templates")
            )
        )
        
        self.caddy_api_url = "http://caddy:2019"
    
    def _replace_env_vars(self, text: str) -> str:
        """Замена переменных окружения в строке вида ${VAR:-default}."""
        import re
        import os
        
        def replace(match):
            var_name = match.group(1)
            default = match.group(2) if match.group(2) else ''
            value = os.getenv(var_name, default)
            return value
        
        pattern = r'\$\{([A-Za-z0-9_]+)(?:\:-([^}]*))?\}'
        return re.sub(pattern, replace, text)

    async def regenerate_all(self, services: Dict[str, ServiceManifest]):
        """Перегенерация всех конфигов сервисов"""
        # Удаляем старые конфиги (все .caddy кроме _subfolder_*.caddy.inc — ручных)
        for old_conf in self.conf_d.glob("*.caddy"):
            if not old_conf.name.startswith("_"):
                old_conf.unlink()
            # Также удаляем старые _subfolder если они были сгенерированы (не .inc)
            elif old_conf.name.startswith("_subfolder_") and not old_conf.name.endswith(".caddy.inc"):
                old_conf.unlink()
        
        # Группируем сервисы по типу routing
        domain_services = []
        subfolder_services = {}  # base_domain -> list of services
        port_services = []
        
        for service in services.values():
            for route in service.routing:
                if route.type == "domain":
                    domain_services.append((service, route))
                elif route.type == "subfolder":
                    base = self._replace_env_vars(route.base_domain)
                    if base not in subfolder_services:
                        subfolder_services[base] = []
                    subfolder_services[base].append((service, route))
                elif route.type == "port":
                    port_services.append((service, route))
        
        # Генерируем конфиги для отдельных доменов
        for service, route in domain_services:
            await self._generate_domain_config(service, route)
        
        # Генерируем конфиги для подпапок (группируем по base_domain)
        for base_domain, svc_routes in subfolder_services.items():
            await self._generate_subfolder_config(base_domain, svc_routes)
        
        # Генерируем конфиги для портов
        for service, route in port_services:
            await self._generate_port_config(service, route)
        
        # Перезагружаем Caddy
        await self.reload_caddy()
    
    async def _generate_domain_config(
        self,
        service: ServiceManifest,
        route
    ):
        """Генерация конфига для отдельного домена"""
        try:
            template = self.jinja.get_template("domain.caddy.j2")
        except Exception as e:
            logger.error(f"Template domain.caddy.j2 not found: {e}")
            return

        # Заменяем переменные окружения в домене
        domain = self._replace_env_vars(route.domain) if route.domain else None

        content = template.render(
            service=service,
            route=route,
            domain=domain,
            generated_at=datetime.now(timezone.utc).isoformat()
        )

        # Если у сервиса несколько доменов — добавляем домен в имя файла
        domain_routes = [r for r in service.routing if r.type == "domain"]
        if len(domain_routes) > 1:
            # Несколько доменов: support_help.openedu.urfu.ru.caddy
            safe_domain = domain.replace(".", "_") if domain else "unknown"
            config_file = self.conf_d / f"{service.name}_{safe_domain}.caddy"
        else:
            config_file = self.conf_d / f"{service.name}.caddy"

        async with aiofiles.open(config_file, 'w') as f:
            await f.write(content)

        logger.info(f"Generated domain config for {service.name} -> {domain}")
    
    async def _generate_subfolder_config(
        self,
        base_domain: str,
        svc_routes: list
    ):
        """Генерация конфига для подпапок одного домена"""
        try:
            template = self.jinja.get_template("subfolder.caddy.j2")
        except Exception as e:
            logger.error(f"Template subfolder.caddy.j2 not found: {e}")
            return
        
        # Заменяем переменные окружения в base_domain
        resolved_base_domain = self._replace_env_vars(base_domain)
        
        content = template.render(
            base_domain=resolved_base_domain,
            services=svc_routes,
            generated_at=datetime.now(timezone.utc).isoformat()
        )
        
        # Санитизация имени файла
        safe_domain = resolved_base_domain.replace(".", "_")
        config_file = self.conf_d / f"_subfolder_{safe_domain}.caddy"
        
        async with aiofiles.open(config_file, 'w') as f:
            await f.write(content)
        
        logger.info(f"Generated subfolder config for {resolved_base_domain}")
    
    async def _generate_port_config(self, service: ServiceManifest, route):
        """Генерация конфига для порта"""
        try:
            template = self.jinja.get_template("port.caddy.j2")
        except Exception as e:
            logger.error(f"Template port.caddy.j2 not found: {e}")
            return
        
        content = template.render(
            service=service,
            route=route,
            generated_at=datetime.now(timezone.utc).isoformat()
        )
        
        config_file = self.conf_d / f"{service.name}_port.caddy"
        async with aiofiles.open(config_file, 'w') as f:
            await f.write(content)
        
        logger.info(f"Generated port config for {service.name}")
    
    async def reload_caddy(self):
        """Перезагрузка конфигурации Caddy через API"""
        try:
            async with aiohttp.ClientSession() as session:
                # Загрузка нового конфига
                main_caddyfile_content = await self._read_main_caddyfile()
                
                async with session.post(
                    f"{self.caddy_api_url}/load",
                    headers={"Content-Type": "text/caddyfile"},
                    data=main_caddyfile_content
                ) as response:
                    if response.status != 200:
                        error = await response.text()
                        logger.error(f"Caddy reload failed: {error}")
                        raise Exception(f"Caddy reload failed: {error}")
                    else:
                        logger.info("Caddy configuration reloaded successfully")
                    
        except aiohttp.ClientError as e:
            logger.error(f"Error connecting to Caddy API: {e}")
            # Fallback: reload через Docker
            try:
                import docker
                client = docker.from_env()
                container = client.containers.get("caddy")
                container.kill(signal="SIGUSR1")
                logger.info("Caddy reloaded via SIGUSR1 signal")
            except Exception as docker_error:
                logger.error(f"Failed to reload Caddy via Docker: {docker_error}")
        except Exception as e:
            logger.error(f"Unexpected error during Caddy reload: {e}")
    
    async def _read_main_caddyfile(self) -> str:
        """Чтение главного Caddyfile"""
        caddyfile_path = self.config_path / "Caddyfile"
        if not caddyfile_path.exists():
            # Создаем минимальный Caddyfile если его нет
            default_content = "{\n    admin 0.0.0.0:2019\n}\n\nimport /etc/caddy/conf.d/*.caddy\n"
            async with aiofiles.open(caddyfile_path, 'w') as f:
                await f.write(default_content)
            return default_content
        
        async with aiofiles.open(caddyfile_path, 'r') as f:
            return await f.read()