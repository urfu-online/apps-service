"""Переиспользуемые Pydantic-валидаторы и константы для Master API.

Все state-changing endpoints обязаны валидировать входные данные на уровне
Pydantic-схем, а не полагаться на валидацию в CLI или shell-скриптах.

Добавлено в Шаге 15 (P1). Содержит:
- ``SERVICE_NAME_RE`` — имена сервисов
- ``SNAPSHOT_ID_RE`` — snapshot_id бэкапов
- ``DOMAIN_RE`` — доменные имена / sub-домены
- Pydantic field_validators и хелперы для оборачивания в ``HTTPException(400)``.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from pydantic import field_validator

# Имя сервиса: латиница/цифры/_.-, начинается с буквы/цифры. Длина (1..128)
# контролируется Pydantic-полем (``max_length=128``), см. ``ServiceNamePath``
# в ``app/api/routes/services.py``. Регулярное выражение совпадает с
# Pydantic-pattern 1-в-1, чтобы убрать drift risk между двумя валидаторами.
SERVICE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
SERVICE_NAME_HINT = (
    "Допустимо: 1..128 символов, латиница/цифры/_.-; "
    "первый символ — буква или цифра."
)

# Snapshot_id Kopia: k[alphanumeric], минимум 1 символ после k
SNAPSHOT_ID_RE = re.compile(r"^k[a-zA-Z0-9]+$")

# Домен: только буквы/цифры/точки/дефисы, без слэшей и протоколов
DOMAIN_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.-]*[a-zA-Z0-9]$")
DOMAIN_HINT = (
    "Допустимо: только буквы, цифры, точки и дефисы; "
    "без протокола и пути."
)


def validate_service_name_field(v: str) -> str:
    """Валидатор имени сервиса для Pydantic v2 field_validator."""
    if not isinstance(v, str) or not v:
        raise ValueError(f"Invalid service name. {SERVICE_NAME_HINT}")
    if "/" in v or "\\" in v or ".." in v:
        raise ValueError(f"Invalid service name. {SERVICE_NAME_HINT}")
    if not SERVICE_NAME_RE.fullmatch(v):
        raise ValueError(f"Invalid service name. {SERVICE_NAME_HINT}")
    return v.lower()


def validate_snapshot_id_field(v: str) -> str:
    """Валидатор snapshot_id для Pydantic v2 field_validator."""
    if not isinstance(v, str) or not SNAPSHOT_ID_RE.fullmatch(v):
        raise ValueError(
            "Invalid snapshot_id format. Expected: k[alphanumeric], e.g. k1a2b3c4"
        )
    return v


def validate_domain_field(v: str) -> str:
    """Валидатор доменного имени для Pydantic v2 field_validator."""
    if not isinstance(v, str) or not DOMAIN_RE.fullmatch(v):
        raise ValueError(f"Invalid domain. {DOMAIN_HINT}")
    return v.lower()


def validate_target_path(v: Optional[str]) -> Optional[str]:
    """Валидатор target-пути для бэкапа restore."""
    if v is None:
        return v
    if not isinstance(v, str):
        raise ValueError("target must be a string")
    if ".." in Path(v).parts:
        raise ValueError("target must not contain '..'")
    return v


def service_name_field_validator():
    """Фабрика ``@field_validator`` для имени сервиса в Pydantic v2."""

    @field_validator("name", check_fields=False)
    @classmethod
    def _validator(cls, v: str) -> str:  # noqa: D401
        return validate_service_name_field(v)

    return _validator


def raise_400(detail: str) -> None:
    """Удобный хелпер для ``HTTPException(400)`` с единым форматом."""
    raise HTTPException(status_code=400, detail=detail)
