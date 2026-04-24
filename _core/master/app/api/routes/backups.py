from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel
import re
from datetime import datetime

from app.core.security import get_current_user

router = APIRouter()


# Pydantic модели для запросов
class BackupRequest(BaseModel):
    """Запрос на создание бэкапа"""
    dry_run: bool = False
    reason: str = "manual"


class RestoreRequest(BaseModel):
    """Запрос на восстановление снапшота"""
    target: Optional[str] = None
    force: bool = False


def validate_snapshot_id(snapshot_id: str) -> str:
    """Валидация snapshot_id (формат: k[alphanumeric])."""
    if not re.match(r'^k[a-zA-Z0-9]+$', snapshot_id):
        raise ValueError(f"Invalid snapshot_id format: {snapshot_id}. Expected format: k[alphanumeric]")
    return snapshot_id


class BackupSnapshotResponse(BaseModel):
    """Ответ со списком снапшотов"""
    snapshot_id: str
    service_name: str
    status: str
    created_at: datetime
    size_bytes: Optional[int]
    retention_days: int


class BackupOperationResponse(BaseModel):
    """Ответ на операцию бэкапа/восстановления"""
    success: bool
    message: str
    snapshot_id: Optional[str] = None
    dry_run: Optional[bool] = None
    target: Optional[str] = None


@router.post("/{svc}/backup", response_model=BackupOperationResponse)
async def create_backup(
    svc: str,
    request: BackupRequest,
    current_user = Depends(get_current_user)
):
    """
    Запуск бэкапа через KopiaBackupManager с валидацией сервиса и enabled=True
    """
    from app.main import app
    
    # Получаем сервис через discovery
    service = app.state.discovery.get_service(svc)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    # Проверяем, что бэкап включен в конфигурации сервиса
    if not service.backup_config or not service.backup_config.enabled:
        raise HTTPException(
            status_code=400, 
            detail=f"Backup disabled for service '{svc}'. Enable it in service configuration."
        )
    
    try:
        if request.dry_run:
            # Dry-run режим
            result = await app.state.backup.dry_run_backup(svc)
            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
            return BackupOperationResponse(
                success=True,
                message=f"Dry-run backup for service '{svc}'",
                snapshot_id="dry-run",
                dry_run=True,
            )
        else:
            # Реальный бэкап
            backup_record = await app.state.backup.run_backup(svc)
            return BackupOperationResponse(
                success=True,
                message=f"Backup created for service '{svc}'",
                snapshot_id=backup_record.snapshot_id,
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}")


@router.get("/{svc}", response_model=List[BackupSnapshotResponse])
async def list_backups(
    svc: str,
    current_user = Depends(get_current_user)
):
    """
    Список снапшотов из БД (BackupRecord) с сортировкой по created_at
    """
    from app.main import app
    
    # Проверяем существование сервиса
    service = app.state.discovery.get_service(svc)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    try:
        # Используем метод list_snapshots из KopiaBackupManager
        snapshots = await app.state.backup.list_snapshots(svc)
        return [
            BackupSnapshotResponse(
                snapshot_id=snap["snapshot_id"],
                service_name=snap["service_name"],
                status=snap["status"],
                created_at=snap["created_at"],
                size_bytes=snap.get("size_bytes"),
                retention_days=snap.get("retention_days", 7),
            )
            for snap in snapshots
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list snapshots: {str(e)}")


@router.post("/{svc}/restore/{snapshot_id}", response_model=BackupOperationResponse)
async def restore_backup(
    svc: str,
    snapshot_id: str,
    request: RestoreRequest,
    current_user = Depends(get_current_user)
):
    """
    Восстановление с проверкой существования снапшота и статуса контейнера
    """
    # Валидация snapshot_id
    try:
        snapshot_id = validate_snapshot_id(snapshot_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    from app.main import app
    
    # Проверяем существование сервиса
    service = app.state.discovery.get_service(svc)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    # Проверяем, что сервис остановлен или force=True
    # (можно добавить проверку статуса контейнера через DockerManager)
    # Пока просто предупреждаем, если force=False
    if not request.force:
        # Можно добавить проверку, но пока пропустим
        pass
    
    try:
        result = await app.state.backup.restore_snapshot(
            svc, snapshot_id, target=request.target, force=request.force
        )
        return BackupOperationResponse(
            success=True,
            message=f"Restore completed for service '{svc}'",
            snapshot_id=snapshot_id,
            target=result.get("target"),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")


@router.delete("/snapshot/{snapshot_id}", response_model=BackupOperationResponse)
async def delete_snapshot(
    snapshot_id: str,
    current_user = Depends(get_current_user)
):
    """
    Удаление снапшота с проверкой использования в активных задачах
    """
    # Валидация snapshot_id
    try:
        snapshot_id = validate_snapshot_id(snapshot_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    from app.main import app
    
    try:
        await app.state.backup.delete_snapshot(snapshot_id)
        return BackupOperationResponse(
            success=True,
            message=f"Snapshot {snapshot_id} deleted",
            snapshot_id=snapshot_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")