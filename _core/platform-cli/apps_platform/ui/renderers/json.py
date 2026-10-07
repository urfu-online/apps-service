"""JSON-рендерер ошибок: объект ``{schema_version, error}`` → канал stdout (§12.2).

JSON-ошибка **всегда** в stdout (машинный контракт не смешивается с данными);
``stderr`` остаётся пустым. Цвет не применяется — JSON должен парситься как
есть. Схему задаёт ``PlatformError.to_json()`` (``core/errors.py``, T1);
здесь только сериализация. Печати нет — результат в ``RenderedOut``.
"""

from __future__ import annotations

import json

from apps_platform.core.errors import PlatformError
from apps_platform.ui.renderers import RenderedOut


def render_error(result: object) -> RenderedOut:
    """``PlatformError`` → JSON-объект ошибки в stdout с завершающим переводом строки."""
    if not isinstance(result, PlatformError):
        raise TypeError(f"json-рендерер ожидает PlatformError, получен: {type(result).__name__}")
    payload = json.dumps(result.to_json(), ensure_ascii=False)
    return RenderedOut(stdout=payload + "\n")
