from fastapi import APIRouter, Depends, HTTPException, Path
from typing import List, Optional
from pydantic import BaseModel, field_validator

from app.core.security import get_current_user
from app.core.validators import (
    SERVICE_NAME_HINT,
    validate_service_name_field,
    raise_400,
)

router = APIRouter()

# TODO(arch): добавить endpoint `GET /api/services/{service_name}/urls`.
# Цель: единый источник правды по URL сервисов (вместо чтения compose/Caddyfile эвристиками в CLI).


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


# Валидатор для ``service_name``-параметра в path (Шаг 15)
ServiceNamePath = Path(
    ...,
    min_length=1,
    max_length=128,
    pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$",
    description=f"Имя сервиса. {SERVICE_NAME_HINT}",
)


@router.get("/", response_model=List[ServiceResponse])
async def list_services(
    visibility: Optional[str] = None,
    status: Optional[str] = None,
    current_user = Depends(get_current_user)
):
    """Список всех сервисов"""
    from app.main import app

    services = app.state.discovery.services.values()

    if visibility and visibility not in ("public", "internal", "core"):
        raise_400(f"Invalid visibility '{visibility}'. Allowed: public, internal, core.")

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
    service_name: str = ServiceNamePath,
    current_user = Depends(get_current_user)
):
    """Детали сервиса"""
    from app.main import app

    try:
        service_name = validate_service_name_field(service_name)
    except ValueError as exc:
        raise_400(str(exc))

    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    # Добавляем runtime информацию
    stats = await app.state.docker.get_stats(service)

    return {
        "manifest": service.model_dump(),
        "stats": stats
    }


@router.post("/{service_name}/deploy")
async def deploy_service(
    service_name: str = ServiceNamePath,
    request: DeployRequest = ...,
    current_user = Depends(get_current_user)
):
    """Деплой/редеплой сервиса. Возвращает 207 при partial success (Шаг 16)."""
    from fastapi.responses import JSONResponse

    from app.main import app

    try:
        service_name = validate_service_name_field(service_name)
    except ValueError as exc:
        raise_400(str(exc))

    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    result = await app.state.docker.deploy_service(
        service,
        build=request.build,
        pull=request.pull
    )

    # Шаг 13/16: метрики и регенерация Caddy выполняются только при успешном
    # (или хотя бы частично успешном) деплое. Hard-failed деплой не должен
    # пересчитывать Caddy и засчитываться в счётчик успешных.
    deploy_ok = bool(result.get("success")) or bool(result.get("partial_success"))

    if deploy_ok:
        # Перегенерация Caddy конфигов
        await app.state.discovery.scan_all()
        await app.state.caddy.regenerate_all(app.state.discovery.services)

        # Шаг 13: инкремент метрики
        from app.main import incr_metric
        incr_metric("deploy_total")

    # Шаг 16: 207 Multi-Status при частичном успехе
    if result.get("partial_success"):
        return JSONResponse(
            status_code=207,
            content=result,
        )
    return result


@router.post("/{service_name}/stop")
async def stop_service(
    service_name: str = ServiceNamePath,
    current_user = Depends(get_current_user)
):
    """Остановка сервиса"""
    from app.main import app

    try:
        service_name = validate_service_name_field(service_name)
    except ValueError as exc:
        raise_400(str(exc))

    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    return await app.state.docker.stop_service(service)


@router.post("/{service_name}/restart")
async def restart_service(
    service_name: str = ServiceNamePath,
    current_user = Depends(get_current_user)
):
    """Перезапуск сервиса"""
    from app.main import app

    try:
        service_name = validate_service_name_field(service_name)
    except ValueError as exc:
        raise_400(str(exc))

    service = app.state.discovery.get_service(service_name)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    return await app.state.docker.restart_service(service)
