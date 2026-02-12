from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.core.security import get_current_user
from app.core.database import get_db
from app.models.deployment import Deployment, DeploymentLog

router = APIRouter()


class DeploymentResponse(BaseModel):
    id: int
    service_id: int
    version: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime]
    success: bool
    rollback_available: bool


class DeploymentLogResponse(BaseModel):
    id: int
    deployment_id: int
    level: str
    message: str
    timestamp: datetime


class DeployRequest(BaseModel):
    version: str
    build: bool = True
    pull: bool = False


@router.get("/service/{service_id}", response_model=List[DeploymentResponse])
async def list_deployments(
    service_id: int,
    skip: int = 0,
    limit: int = 100,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Список деплоев для сервиса"""
    deployments = db.query(Deployment).filter(
        Deployment.service_id == service_id
    ).order_by(Deployment.started_at.desc()).offset(skip).limit(limit).all()
    
    return deployments


@router.get("/{deployment_id}", response_model=DeploymentResponse)
async def get_deployment(
    deployment_id: int,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Получение информации о деплое"""
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    return deployment


@router.get("/{deployment_id}/logs", response_model=List[DeploymentLogResponse])
async def get_deployment_logs(
    deployment_id: int,
    level: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Получение логов деплоя"""
    query = db.query(DeploymentLog).filter(DeploymentLog.deployment_id == deployment_id)
    
    if level:
        query = query.filter(DeploymentLog.level == level)
    
    logs = query.order_by(DeploymentLog.timestamp).offset(skip).limit(limit).all()
    return logs


@router.post("/service/{service_id}/deploy", response_model=DeploymentResponse)
async def start_deployment(
    service_id: int,
    request: DeployRequest,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Запуск нового деплоя"""
    # Проверяем существование сервиса
    from app.main import app
    service_manifest = None
    for service in app.state.discovery.services.values():
        if service.id == service_id:
            service_manifest = service
            break
    
    if not service_manifest:
        raise HTTPException(status_code=404, detail="Service not found")
    
    # Создаем запись о деплое
    deployment = Deployment(
        service_id=service_id,
        version=request.version,
        status="pending"
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)
    
    # Запускаем деплой в фоне
    from app.main import app
    import asyncio
    asyncio.create_task(
        _execute_deployment(deployment.id, service_manifest, request)
    )
    
    return deployment


@router.post("/{deployment_id}/rollback", response_model=DeploymentResponse)
async def rollback_deployment(
    deployment_id: int,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Откат деплоя"""
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    if not deployment.rollback_available:
        raise HTTPException(status_code=400, detail="Rollback not available for this deployment")
    
    # Помечаем деплой как откатываемый
    deployment.status = "rolling_back"
    db.commit()
    
    # Запускаем откат в фоне
    from app.main import app
    import asyncio
    asyncio.create_task(
        _execute_rollback(deployment.id)
    )
    
    return deployment


async def _execute_deployment(deployment_id: int, service, request: DeployRequest):
    """Выполнение деплоя в фоне"""
    from app.main import app
    db = next(get_db())
    
    try:
        # Обновляем статус
        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        deployment.status = "in_progress"
        db.commit()
        
        # Выполняем деплой через DockerManager
        result = await app.state.docker.deploy_service(
            service,
            build=request.build,
            pull=request.pull
        )
        
        # Обновляем статус
        deployment.status = "completed" if result["success"] else "failed"
        deployment.success = result["success"]
        deployment.finished_at = datetime.utcnow()
        deployment.rollback_available = result["success"]
        
        # Сохраняем логи
        if result["logs"]:
            for log_line in result["logs"]:
                if log_line.strip():  # Пропускаем пустые строки
                    log_entry = DeploymentLog(
                        deployment_id=deployment.id,
                        level="info",
                        message=log_line
                    )
                    db.add(log_entry)
        
        db.commit()
        
        # Отправляем уведомление
        await app.state.notifier.send_deployment_notification(
            service.name,
            request.version,
            "success" if result["success"] else "failed",
            "\n".join(result["logs"][-10:]) if result["logs"] else None  # Последние 10 строк логов
        )
        
    except Exception as e:
        # Обновляем статус при ошибке
        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        deployment.status = "failed"
        deployment.success = False
        deployment.finished_at = datetime.utcnow()
        
        # Сохраняем ошибку в логах
        log_entry = DeploymentLog(
            deployment_id=deployment.id,
            level="error",
            message=str(e)
        )
        db.add(log_entry)
        db.commit()
        
        # Отправляем уведомление об ошибке
        await app.state.notifier.send_deployment_notification(
            service.name,
            request.version,
            "failed",
            str(e)
        )


async def _execute_rollback(deployment_id: int):
    """Выполнение отката в фоне"""
    from app.main import app
    db = next(get_db())
    
    try:
        # Получаем деплой
        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if not deployment:
            return
        
        # Получаем сервис
        service_manifest = app.state.discovery.get_service_by_id(deployment.service_id)
        if not service_manifest:
            raise HTTPException(status_code=404, detail="Service not found")
        
        # Обновляем статус
        deployment.status = "rolling_back"
        db.commit()
        
        # Здесь должна быть логика отката
        # В упрощенной реализации просто перезапускаем предыдущую версию
        result = await app.state.docker.restart_service(service_manifest)
        
        # Обновляем статус
        deployment.status = "rollback_completed" if result["success"] else "rollback_failed"
        deployment.finished_at = datetime.utcnow()
        db.commit()
        
        # Отправляем уведомление
        await app.state.notifier.send(
            f"🔄 Rollback {'completed' if result['success'] else 'failed'} for {service_manifest.name}"
        )
        
    except Exception as e:
        # Обновляем статус при ошибке
        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        deployment.status = "rollback_failed"
        deployment.finished_at = datetime.utcnow()
        
        # Сохраняем ошибку в логах
        log_entry = DeploymentLog(
            deployment_id=deployment.id,
            level="error",
            message=str(e)
        )
        db.add(log_entry)
        db.commit()
        
        # Отправляем уведомление об ошибке
        await app.state.notifier.send(
            f"❌ Rollback failed for {service_manifest.name}: {e}"
        )