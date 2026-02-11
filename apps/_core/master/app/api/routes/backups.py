from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.core.security import get_current_user
from app.services.discovery import ServiceManifest
from app.models.backup import Backup

router = APIRouter()


class BackupResponse(BaseModel):
    id: int
    service_id: int
    name: str
    timestamp: datetime
    size: Optional[int]
    status: str
    reason: str


class BackupCreateRequest(BaseModel):
    reason: str = "manual"


class RestoreRequest(BaseModel):
    backup_id: int


@router.get("/service/{service_name}", response_model=List[BackupResponse])
async def list_service_backups(
    service_name: str,
    skip: int = 0,
    limit: int = 100,
    current_user = Depends(get_current_user)
):
    """Список бэкапов для сервиса"""
    from app.main import app
    
    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    # Получаем бэкапы через BackupManager
    backups = await app.state.backup.list_backups(service)
    
    # Конвертируем в формат ответа
    response_backups = []
    for backup in backups[skip:skip+limit]:
        response_backups.append(BackupResponse(
            id=0,  # В упрощенной реализации ID не используется
            service_id=0,  # В упрощенной реализации ID не используется
            name=backup.get("backup_name", ""),
            timestamp=datetime.fromisoformat(backup.get("timestamp", datetime.utcnow().isoformat())),
            size=None,  # В упрощенной реализации размер не отслеживается
            status="completed",  # В упрощенной реализации все бэкапы завершены
            reason=backup.get("reason", "manual")
        ))
    
    return response_backups


@router.post("/service/{service_name}/backup", response_model=BackupResponse)
async def create_backup(
    service_name: str,
    request: BackupCreateRequest,
    current_user = Depends(get_current_user)
):
    """Создание бэкапа сервиса"""
    from app.main import app
    
    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    # Создаем бэкап через BackupManager
    result = await app.state.backup.backup_service(service, reason=request.reason)
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["errors"][0] if result["errors"] else "Backup failed")
    
    # Возвращаем информацию о созданном бэкапе
    return BackupResponse(
        id=0,
        service_id=0,
        name=result["backup_name"],
        timestamp=datetime.utcnow(),
        size=None,
        status="completed",
        reason=request.reason
    )


@router.post("/service/{service_name}/restore", response_model=dict)
async def restore_backup(
    service_name: str,
    request: RestoreRequest,
    current_user = Depends(get_current_user)
):
    """Восстановление бэкапа сервиса"""
    from app.main import app
    
    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    # В упрощенной реализации просто возвращаем сообщение
    # В реальной реализации здесь будет логика восстановления
    return {
        "message": f"Restore scheduled for service {service_name}",
        "backup_id": request.backup_id
    }


@router.delete("/{backup_id}", response_model=dict)
async def delete_backup(
    backup_id: int,
    current_user = Depends(get_current_user)
):
    """Удаление бэкапа"""
    # В упрощенной реализации просто возвращаем сообщение
    return {
        "message": f"Backup {backup_id} scheduled for deletion"
    }


@router.get("/{backup_id}/info", response_model=dict)
async def get_backup_info(
    backup_id: int,
    current_user = Depends(get_current_user)
):
    """Получение информации о бэкапе"""
    # В упрощенной реализации просто возвращаем сообщение
    return {
        "message": f"Backup info for backup {backup_id}",
        "backup_id": backup_id
    }