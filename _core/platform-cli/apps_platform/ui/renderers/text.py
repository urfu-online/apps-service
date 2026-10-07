"""Текстовый рендерер ошибок: 4 вопроса §12.3 → канал stderr (§12.1).

Многострочный человекочитаемый текст на русском (§7.6), маркер ``✘`` — как в
§7.5; без таблиц и без зависимых от ширины конструкций (переносы по ширине
появятся в P2 с таблицами). Печати нет — результат возвращается в
``RenderedOut``; красный/dim оформляется ANSI-кодами только если передана
политика цвета канала stderr (по умолчанию цвета выключены).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps_platform.core.errors import PlatformError
from apps_platform.ui.renderers import RenderedOut

if TYPE_CHECKING:
    from apps_platform.ui.console import ColorPolicy

_RED = "\x1b[31m"
_DIM = "\x1b[2m"
_RESET = "\x1b[0m"


def render_error(result: object, color_policy: ColorPolicy | None = None) -> RenderedOut:
    """``PlatformError`` → текст ошибки в stderr, пустой stdout.

    Структура по §12.3: «что произошло» — ``message`` (первый вопрос, включая
    «что CLI успел сделать», если это передано в message), «с каким объектом» —
    ``object``, «что проверить дальше» — ``hint`` строкой «Подсказка: …».
    Строки message после первой печатаются с отступом 2. ``color_policy`` —
    политика канала stderr; ``None`` → без цвета (дефолт в тестах).
    """
    if not isinstance(result, PlatformError):
        raise TypeError(f"текстовый рендерер ожидает PlatformError, получен: {type(result).__name__}")

    color = color_policy.stderr_colors() if color_policy is not None else False
    red = _RED if color else ""
    dim = _DIM if color else ""
    reset = _RESET if color else ""

    message_lines = result.message.splitlines() or [""]
    lines = [f"{red}✘ {message_lines[0]}{reset}"]
    lines.extend(f"  {line}" for line in message_lines[1:])
    if result.object is not None:
        lines.append(f"  Объект: {result.object}")
    if result.hint:
        hint_line = f"  Подсказка: {result.hint}"
        lines.append(f"{dim}{hint_line}{reset}" if color else hint_line)

    return RenderedOut(stderr="\n".join(lines) + "\n")
