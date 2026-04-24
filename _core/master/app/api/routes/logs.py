import logging
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timezone

from app.core.security import get_current_user

router = APIRouter()


class LogEntryResponse(BaseModel):
    timestamp: str
    level: str
    message: str


class LogSearchRequest(BaseModel):
    query: str
    limit: int = 50
    case_sensitive: bool = False
    full_scan: bool = False


@router.get("/service/{service_name}", response_model=List[str])
async def get_service_logs(
    service_name: str,
    tail: int = 100,
    since: Optional[str] = None,
    current_user = Depends(get_current_user)
):
    """Получение логов сервиса через LogManager"""
    from app.main import app

    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    logs = await app.state.log_manager.get_service_logs(service, tail=tail, since=since)
    return logs


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

    results = await app.state.log_manager.search_logs(
        service,
        query=request.query,
        limit=request.limit,
        case_sensitive=request.case_sensitive,
        full_scan=request.full_scan
    )
    return results


@router.get("/service/{service_name}/stats")
async def get_log_stats(
    service_name: str,
    full_scan: bool = False,
    current_user = Depends(get_current_user)
):
    """Получение статистики по логам сервиса"""
    from app.main import app

    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    stats = await app.state.log_manager.get_log_stats(service, full_scan=full_scan)
    return stats


@router.get("/service/{service_name}/export")
async def export_service_logs(
    service_name: str,
    current_user = Depends(get_current_user)
):
    """Экспорт логов сервиса в файл.

    ⚠️ Файл сохраняется в volume-mounted директорию,
    чтобы не удалиться при рестарте контейнера.
    """
    from app.main import app
    from fastapi.responses import FileResponse

    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    try:
        export_path = await app.state.log_manager.export_logs(service)
        return FileResponse(
            path=export_path,
            filename=export_path.name,
            media_type='text/plain'
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Export failed for {service_name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to export logs")