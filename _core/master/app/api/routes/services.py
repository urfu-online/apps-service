from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel

from app.core.security import get_current_user
from app.services.discovery import ServiceManifest
from app.services.discovery import ServiceDiscovery

router = APIRouter()


class ServiceResponse(BaseModel):
    name: str
    display_name: Optional[str]
    version: str
    status: str
    visibility: str
    type: str


class DeployRequest(BaseModel):
    build: bool = True
    pull: bool = False


@router.get("/", response_model=List[ServiceResponse])
async def list_services(
    visibility: Optional[str] = None,
    status: Optional[str] = None,
    current_user = Depends(get_current_user)
):
    """Список всех сервисов"""
    from app.main import app
    
    services = app.state.discovery.services.values()
    
    if visibility:
        services = [s for s in services if s.visibility == visibility]
    if status:
        services = [s for s in services if s.status == status]
    
    return [ServiceResponse(
        name=s.name,
        display_name=s.display_name,
        version=s.version,
        status=s.status,
        visibility=s.visibility,
        type=s.type
    ) for s in services]


@router.get("/{service_name}")
async def get_service(
    service_name: str,
    current_user = Depends(get_current_user)
):
    """Детали сервиса"""
    from app.main import app
    
    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    # Добавляем runtime информацию
    stats = await app.state.docker.get_stats(service)
    
    return {
        "manifest": service.dict(),
        "stats": stats
    }


@router.post("/{service_name}/deploy")
async def deploy_service(
    service_name: str,
    request: DeployRequest,
    current_user = Depends(get_current_user)
):
    """Деплой/редеплой сервиса"""
    from app.main import app
    
    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    result = await app.state.docker.deploy_service(
        service, 
        build=request.build,
        pull=request.pull
    )
    
    # Перегенерация Caddy конфигов
    await app.state.discovery.scan_all()
    await app.state.caddy.regenerate_all(app.state.discovery.services)
    
    return result


@router.post("/{service_name}/stop")
async def stop_service(
    service_name: str,
    current_user = Depends(get_current_user)
):
    """Остановка сервиса"""
    from app.main import app
    
    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    return await app.state.docker.stop_service(service)


@router.post("/{service_name}/restart")
async def restart_service(
    service_name: str,
    current_user = Depends(get_current_user)
):
    """Перезапуск сервиса"""
    from app.main import app
    
    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    return await app.state.docker.restart_service(service)