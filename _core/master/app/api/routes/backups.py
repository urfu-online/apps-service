from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timezone

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
            timestamp=datetime.fromisoformat(backup.get("timestamp", datetime.now(timezone.utc).isoformat())),
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
        timestamp=datetime.now(timezone.utc),
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

    # Получаем список бэкапов и находим нужный по индексу
    backups = await app.state.backup.list_backups(service)
    if request.backup_id < 0 or request.backup_id >= len(backups):
        raise HTTPException(status_code=404, detail="Backup not found")

    backup_data = backups[request.backup_id]
    result = await app.state.backup.restore_service(service, backup_data["backup_name"])

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("message", "Restore failed"))

    return {
        "message": f"Restore completed for {service_name}",
        "restored_files": result.get("restored_files", []),
        "restored_databases": result.get("restored_databases", []),
        "errors": result.get("errors", [])
    }


@router.delete("/{backup_name}", response_model=dict)
async def delete_backup(
    service_name: str,
    backup_name: str,
    current_user = Depends(get_current_user)
):
    """Удаление бэкапа"""
    from app.main import app
    import shutil

    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    backup_path = app.state.backup.backup_base_path / service_name / backup_name
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")

    shutil.rmtree(backup_path)
    return {"message": f"Backup {backup_name} deleted"}


@router.get("/{backup_name}/info", response_model=dict)
async def get_backup_info(
    service_name: str,
    backup_name: str,
    current_user = Depends(get_current_user)
):
    """Получение информации о бэкапе"""
    from app.main import app
    import aiofiles
    import json

    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    backup_path = app.state.backup.backup_base_path / service_name / backup_name
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")

    metadata_file = backup_path / "metadata.json"
    if not metadata_file.exists():
        raise HTTPException(status_code=404, detail="Backup metadata not found")

    async with aiofiles.open(metadata_file, 'r') as f:
        metadata = json.loads(await f.read())

    return metadata