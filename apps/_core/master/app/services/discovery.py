from pathlib import Path
from typing import Dict, Optional, List
import yaml
from pydantic import BaseModel, Field
from datetime import datetime
import asyncio
import aiofiles
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from app.models.service import Service, ServiceType, ServiceVisibility, ServiceStatus, RoutingConfig, RoutingType, HealthConfig, BackupConfig
from app.core.database import db_manager
from app.core.events import event_bus

# Настройка логирования
logger = logging.getLogger(__name__)


class RoutingConfigModel(BaseModel):
    """Модель конфигурации маршрутизации"""
    type: str  # domain, subfolder, port
    domain: Optional[str] = None
    base_domain: Optional[str] = None
    path: Optional[str] = None
    port: Optional[int] = None
    strip_prefix: bool = True
    internal_port: int = 8000


class HealthConfigModel(BaseModel):
    """Модель конфигурации проверки здоровья"""
    enabled: bool = True
    endpoint: str = "/health"
    interval: str = "30s"
    timeout: str = "10s"
    retries: int = 3


class BackupConfigModel(BaseModel):
    """Модель конфигурации бэкапов"""
    enabled: bool = False
    schedule: str = "0 2 * * *"
    retention: int = 7
    paths: list[str] = []
    databases: list[dict] = []


class ServiceManifest(BaseModel):
    """Модель манифеста сервиса"""
    name: str
    display_name: Optional[str] = None
    version: str = "1.0.0"
    description: str = ""
    type: str = "docker-compose"
    visibility: str = "internal"
    routing: list[RoutingConfigModel] = []
    health: HealthConfigModel = HealthConfigModel()
    backup: BackupConfigModel = BackupConfigModel()
    tags: list[str] = []
    
    # Runtime info
    path: Optional[Path] = None
    status: str = "unknown"
    last_deployed: Optional[datetime] = None
    container_ids: list[str] = []


class ServiceDiscovery:
    """Обнаружение и управление сервисами"""
    
    def __init__(self, services_path: str):
        self.services_path = Path(services_path)
        self.services: Dict[str, ServiceManifest] = {}
        self.observer = Observer()
        self._setup_watcher()
    
    def _setup_watcher(self):
        """Настройка наблюдателя за изменениями в директориях сервисов"""
        event_handler = ServiceChangeHandler(self)
        self.observer.schedule(event_handler, str(self.services_path), recursive=True)
        self.observer.start()
        logger.info(f"Started watching {self.services_path} for service changes")
    
    async def scan_all(self) -> Dict[str, ServiceManifest]:
        """Сканирование всех директорий сервисов"""
        self.services = {}
        
        for visibility in ['public', 'internal']:
            visibility_path = self.services_path / visibility
            if not visibility_path.exists():
                continue
                
            for service_dir in visibility_path.iterdir():
                if service_dir.is_dir():
                    manifest = await self._load_service(service_dir, visibility)
                    if manifest:
                        self.services[manifest.name] = manifest
        
        return self.services
    
    async def _load_service(
        self, 
        service_dir: Path, 
        visibility: str
    ) -> Optional[ServiceManifest]:
        """Загрузка манифеста сервиса"""
        manifest_path = service_dir / "service.yml"
        
        # Если нет service.yml, пробуем создать минимальный из docker-compose
        if not manifest_path.exists():
            compose_path = service_dir / "docker-compose.yml"
            if compose_path.exists():
                return await self._create_minimal_manifest(
                    service_dir, visibility
                )
            return None
        
        try:
            async with aiofiles.open(manifest_path, 'r') as f:
                content = await f.read()
                data = yaml.safe_load(content)
            
            manifest = ServiceManifest(**data)
            manifest.path = service_dir
            manifest.visibility = visibility
            
            # Получить статус из Docker
            manifest.status = await self._get_docker_status(manifest)
            
            return manifest
            
        except Exception as e:
            logger.error(f"Error loading {manifest_path}: {e}")
            return None
    
    async def _create_minimal_manifest(
        self, 
        service_dir: Path, 
        visibility: str
    ) -> ServiceManifest:
        """Создание минимального манифеста для сервиса без service.yml"""
        return ServiceManifest(
            name=service_dir.name,
            display_name=service_dir.name.replace('-', ' ').title(),
            type="docker-compose",
            visibility=visibility,
            path=service_dir,
            routing=[RoutingConfigModel(
                type="subfolder",
                base_domain="apps.urfu.online",
                path=f"/{service_dir.name}"
            )]
        )
    
    async def _get_docker_status(self, manifest: ServiceManifest) -> str:
        """Получение статуса Docker контейнеров сервиса"""
        # В упрощенной версии возвращаем неизвестный статус
        # В реальной реализации здесь будет взаимодействие с Docker API
        return "unknown"
    
    def get_service(self, name: str) -> Optional[ServiceManifest]:
        """Получение сервиса по имени"""
        return self.services.get(name)
    
    def get_services_by_visibility(
        self, 
        visibility: str
    ) -> Dict[str, ServiceManifest]:
        """Получение сервисов по видимости"""
        return {
            name: svc for name, svc in self.services.items()
            if svc.visibility == visibility
        }
    
    async def sync_with_database(self):
        """Синхронизация обнаруженных сервисов с базой данных"""
        db = next(db_manager.get_db())
        
        for service_manifest in self.services.values():
            # Проверяем, существует ли сервис в базе данных
            db_service = db.query(Service).filter(Service.name == service_manifest.name).first()
            
            if not db_service:
                # Создаем новый сервис в базе данных
                db_service = Service(
                    name=service_manifest.name,
                    display_name=service_manifest.display_name,
                    version=service_manifest.version,
                    description=service_manifest.description,
                    type=service_manifest.type,
                    visibility=service_manifest.visibility,
                    status=service_manifest.status
                )
                db.add(db_service)
                db.commit()
                db.refresh(db_service)
                logger.info(f"Created new service in database: {service_manifest.name}")
            else:
                # Обновляем существующий сервис
                db_service.display_name = service_manifest.display_name
                db_service.version = service_manifest.version
                db_service.description = service_manifest.description
                db_service.type = service_manifest.type
                db_service.visibility = service_manifest.visibility
                db_service.status = service_manifest.status
                db.commit()
                logger.info(f"Updated service in database: {service_manifest.name}")
        
        # Удаляем сервисы, которые больше не существуют
        db_service_names = [s.name for s in db.query(Service).all()]
        manifest_names = list(self.services.keys())
        
        for service_name in db_service_names:
            if service_name not in manifest_names:
                db_service = db.query(Service).filter(Service.name == service_name).first()
                if db_service:
                    db.delete(db_service)
                    logger.info(f"Deleted service from database: {service_name}")
        
        db.commit()


class ServiceChangeHandler(FileSystemEventHandler):
    """Обработчик изменений в файлах сервисов"""
    
    def __init__(self, discovery: ServiceDiscovery):
        self.discovery = discovery
        super().__init__()
    
    def on_modified(self, event):
        """Обработка изменения файла"""
        if event.is_directory:
            return
        
        # Проверяем, что изменение касается service.yml или docker-compose.yml
        if 'service.yml' in event.src_path or 'docker-compose.yml' in event.src_path:
            logger.info(f"Service configuration changed: {event.src_path}")
            # Отправляем событие об изменении сервиса
            asyncio.create_task(event_bus.emit("service.config.changed", {
                "path": event.src_path
            }))
    
    def on_created(self, event):
        """Обработка создания файла"""
        if event.is_directory:
            return
        
        # Проверяем, что создан service.yml или docker-compose.yml
        if 'service.yml' in event.src_path or 'docker-compose.yml' in event.src_path:
            logger.info(f"New service configuration created: {event.src_path}")
            # Отправляем событие о создании сервиса
            asyncio.create_task(event_bus.emit("service.config.created", {
                "path": event.src_path
            }))
    
    def on_deleted(self, event):
        """Обработка удаления файла"""
        if event.is_directory:
            return
        
        # Проверяем, что удален service.yml или docker-compose.yml
        if 'service.yml' in event.src_path or 'docker-compose.yml' in event.src_path:
            logger.info(f"Service configuration deleted: {event.src_path}")
            # Отправляем событие об удалении сервиса
            asyncio.create_task(event_bus.emit("service.config.deleted", {
                "path": event.src_path
            }))