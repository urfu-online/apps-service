from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timezone

from app.core.security import get_current_user
from app.services.discovery import ServiceManifest

router = APIRouter()


class LogEntryResponse(BaseModel):
    timestamp: str
    level: str
    message: str


class LogSearchRequest(BaseModel):
    query: str
    limit: int = 100


@router.get("/service/{service_name}", response_model=List[str])
async def get_service_logs(
    service_name: str,
    tail: int = 100,
    since: Optional[str] = None,
    current_user = Depends(get_current_user)
):
    """Получение логов сервиса"""
    from app.main import app
    
    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    logs = await app.state.docker.get_logs(service, tail=tail, since=since)
    return logs.split("\n")


@router.post("/service/{service_name}/search", response_model=List[str])
async def search_service_logs(
    service_name: str,
    request: LogSearchRequest,
    current_user = Depends(get_current_user)
):
    """Поиск по логам сервиса"""
    from app.main import app
    
    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    # Получаем логи через LogManager
    logs = await app.state.log_manager.get_service_logs(service, tail=1000)
    
    # Фильтруем по запросу
    matching_logs = [log for log in logs if request.query.lower() in log.lower()]
    
    # Возвращаем последние N совпадений
    return matching_logs[-request.limit:]


@router.get("/service/{service_name}/stats")
async def get_log_stats(
    service_name: str,
    current_user = Depends(get_current_user)
):
    """Получение статистики по логам сервиса"""
    from app.main import app
    
    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    stats = await app.state.log_manager.get_log_stats(service)
    return stats


@router.get("/service/{service_name}/export")
async def export_service_logs(
    service_name: str,
    current_user = Depends(get_current_user)
):
    """Экспорт логов сервиса"""
    from app.main import app
    
    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    # Генерируем имя файла для экспорта
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    export_filename = f"{service_name}_logs_{timestamp}.txt"
    
    # Здесь должна быть логика экспорта
    # В упрощенной реализации просто возвращаем сообщение
    return {
        "message": f"Logs export scheduled for {service_name}",
        "filename": export_filename
    }