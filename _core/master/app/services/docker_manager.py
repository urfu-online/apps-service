import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
import logging
import docker
from docker.errors import NotFound, APIError

from app.services.discovery import ServiceManifest
from app.services.notifier import TelegramNotifier

# Настройка логирования
logger = logging.getLogger(__name__)


class DockerManager:
    """Управление Docker контейнерами и compose проектами"""

    def __init__(self, notifier: TelegramNotifier):
        self.client = docker.from_env()
        self.notifier = notifier
    
    async def deploy_service(
        self, 
        service: ServiceManifest,
        build: bool = True,
        pull: bool = False
    ) -> Dict[str, Any]:
        """Деплой сервиса"""
        result = {
            "success": False,
            "message": "",
            "logs": []
        }
        
        try:
            if service.type == "docker-compose":
                result = await self._deploy_compose(service, build, pull)
            elif service.type == "docker":
                result = await self._deploy_single(service, build, pull)
            elif service.type == "static":
                result = await self._deploy_static(service)
            
            if result["success"]:
                await self.notifier.send(
                    f"✅ Service {service.name} deployed successfully\n"
                    f"Version: {service.version}"
                )
            else:
                await self.notifier.send(
                    f"❌ Service {service.name} deployment failed\n"
                    f"Error: {result['message']}"
                )
                
        except Exception as e:
            result["success"] = False
            result["message"] = str(e)
            await self.notifier.send(
                f"❌ Service {service.name} deployment error\n"
                f"Error: {e}"
            )
        
        return result
    
    async def _deploy_compose(
        self, 
        service: ServiceManifest,
        build: bool,
        pull: bool
    ) -> Dict[str, Any]:
        """Деплой docker-compose проекта"""
        compose_file = service.path / "docker-compose.yml"
        
        if not compose_file.exists():
            return {
                "success": False,
                "message": "docker-compose.yml not found",
                "logs": []
            }
        
        cmd = ["docker", "compose", "-f", str(compose_file)]
        
        # Добавляем env файл если есть
        env_file = service.path / ".env"
        if env_file.exists():
            cmd.extend(["--env-file", str(env_file)])
        
        # Pull если нужно
        if pull:
            pull_result = await self._run_command(
                cmd + ["pull"]
            )
        
        # Build если нужно
        if build:
            build_result = await self._run_command(
                cmd + ["build", "--no-cache"]
            )
        
        # Up
        up_result = await self._run_command(
            cmd + ["up", "-d", "--remove-orphans"]
        )
        
        return {
            "success": up_result["returncode"] == 0,
            "message": up_result["stderr"] if up_result["returncode"] != 0 else "OK",
            "logs": up_result["stdout"].split("\n")
        }
    
    async def stop_service(self, service: ServiceManifest) -> Dict[str, Any]:
        """Остановка сервиса"""
        if service.type == "docker-compose":
            compose_file = service.path / "docker-compose.yml"
            result = await self._run_command([
                "docker", "compose", "-f", str(compose_file), 
                "down"
            ])
        else:
            # Остановка по label
            containers = self.client.containers.list(
                filters={"label": f"platform.service={service.name}"}
            )
            for container in containers:
                container.stop()
            result = {"returncode": 0, "stdout": "OK", "stderr": ""}
        
        return {
            "success": result["returncode"] == 0,
            "message": result["stderr"] if result["returncode"] != 0 else "OK"
        }
    
    async def restart_service(self, service: ServiceManifest) -> Dict[str, Any]:
        """Перезапуск сервиса"""
        if service.type == "docker-compose":
            compose_file = service.path / "docker-compose.yml"
            result = await self._run_command([
                "docker", "compose", "-f", str(compose_file), 
                "restart"
            ])
        else:
            containers = self.client.containers.list(
                filters={"label": f"platform.service={service.name}"}
            )
            for container in containers:
                container.restart()
            result = {"returncode": 0, "stdout": "OK", "stderr": ""}
        
        return {
            "success": result["returncode"] == 0,
            "message": result["stderr"] if result["returncode"] != 0 else "OK"
        }
    
    async def get_logs(
        self, 
        service: ServiceManifest, 
        tail: int = 100,
        since: Optional[str] = None
    ) -> str:
        """Получение логов сервиса"""
        logs = []
        
        containers = self.client.containers.list(
            all=True,
            filters={"label": f"platform.service={service.name}"}
        )
        
        for container in containers:
            container_logs = container.logs(
                tail=tail,
                since=since,
                timestamps=True
            ).decode('utf-8')
            logs.append(f"=== {container.name} ===\n{container_logs}")
        
        return "\n\n".join(logs)
    
    async def get_stats(self, service: ServiceManifest) -> Dict[str, Any]:
        """Получение статистики использования ресурсов"""
        stats = {}
        
        containers = self.client.containers.list(
            filters={"label": f"platform.service={service.name}"}
        )
        
        for container in containers:
            try:
                container_stats = container.stats(stream=False)
                
                # CPU
                cpu_delta = (
                    container_stats['cpu_stats']['cpu_usage']['total_usage'] -
                    container_stats['precpu_stats']['cpu_usage']['total_usage']
                )
                system_delta = (
                    container_stats['cpu_stats']['system_cpu_usage'] -
                    container_stats['precpu_stats']['system_cpu_usage']
                )
                cpu_percent = (cpu_delta / system_delta) * 100.0 if system_delta > 0 else 0
                
                # Memory
                memory_usage = container_stats['memory_stats'].get('usage', 0)
                memory_limit = container_stats['memory_stats'].get('limit', 1)
                memory_percent = (memory_usage / memory_limit) * 100.0
                
                stats[container.name] = {
                    "cpu_percent": round(cpu_percent, 2),
                    "memory_usage_mb": round(memory_usage / 1024 / 1024, 2),
                    "memory_limit_mb": round(memory_limit / 1024 / 1024, 2),
                    "memory_percent": round(memory_percent, 2),
                    "status": container.status
                }
            except Exception as e:
                logger.error(f"Error getting stats for container {container.name}: {e}")
                stats[container.name] = {
                    "error": str(e)
                }
        
        return stats
    
    async def _run_command(self, cmd: list) -> Dict[str, Any]:
        """Асинхронное выполнение команды"""
        logger.info(f"Running command: {' '.join(cmd)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        result = {
            "returncode": process.returncode,
            "stdout": stdout.decode('utf-8'),
            "stderr": stderr.decode('utf-8')
        }
        
        logger.info(f"Command result: {result}")
        return result