from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, List, Optional
from pydantic import BaseModel
from datetime import datetime, timezone

from app.core.security import get_current_user
from app.services.discovery import ServiceManifest

router = APIRouter()


class HealthResponse(BaseModel):
    service_name: str
    is_healthy: bool
    response_time: float
    last_checked: str
    error: Optional[str] = None


class SystemHealthResponse(BaseModel):
    overall_status: str
    services: List[HealthResponse]
    timestamp: str


@router.get("/", response_model=SystemHealthResponse)
async def get_system_health(
    current_user = Depends(get_current_user)
):
    """Получение общего состояния здоровья системы"""
    from app.main import app
    
    services = app.state.discovery.services.values()
    health_results = []
    
    overall_healthy = True
    
    for service in services:
        try:
            status = await app.state.health_checker.check(service)
            health_results.append(HealthResponse(
                service_name=service.name,
                is_healthy=status.is_healthy,
                response_time=status.response_time,
                last_checked=status.checked_at.isoformat(),
                error=status.error
            ))
            
            if not status.is_healthy:
                overall_healthy = False
        except Exception as e:
            health_results.append(HealthResponse(
                service_name=service.name,
                is_healthy=False,
                response_time=0,
                last_checked="",
                error=str(e)
            ))
            overall_healthy = False
    
    return SystemHealthResponse(
        overall_status="healthy" if overall_healthy else "unhealthy",
        services=health_results,
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@router.get("/service/{service_name}", response_model=HealthResponse)
async def get_service_health(
    service_name: str,
    current_user = Depends(get_current_user)
):
    """Получение состояния здоровья конкретного сервиса"""
    from app.main import app
    
    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    try:
        status = await app.state.health_checker.check(service)
        return HealthResponse(
            service_name=service.name,
            is_healthy=status.is_healthy,
            response_time=status.response_time,
            last_checked=status.checked_at.isoformat(),
            error=status.error
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=Dict[str, int])
async def get_health_stats(
    current_user = Depends(get_current_user)
):
    """Получение статистики по состоянию здоровья"""
    from app.main import app
    
    services = app.state.discovery.services.values()
    healthy_count = 0
    unhealthy_count = 0
    unknown_count = 0
    
    for service in services:
        try:
            status = await app.state.health_checker.check(service)
            if status.is_healthy:
                healthy_count += 1
            else:
                unhealthy_count += 1
        except Exception:
            unknown_count += 1
    
    return {
        "healthy": healthy_count,
        "unhealthy": unhealthy_count,
        "unknown": unknown_count,
        "total": len(services)
    }

