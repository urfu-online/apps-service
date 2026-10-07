"""Контракт рендеринга и реестр рендереров — ADR-003, tech spec §5.

Форматирование только здесь: use case возвращает результат/ошибку, рендерер —
чистая функция ``render(result) -> RenderedOut`` без print и прочих side
effects; в потоки пишет только ``cli.py`` (``stdout`` рендерера → ``sys.stdout``,
``stderr`` → ``sys.stderr``, §12.1).

Реестр — обычный dict в этом модуле, ключ — точный тип результата; наполняет
его composition root (T8), для рендереров ошибок P1 есть ``register_defaults()``.
Отсутствие рендерера для типа → ``AssertionError`` с именем типа: ошибка сборки,
а не рантайма пользователя.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from apps_platform.core.errors import PlatformError

if TYPE_CHECKING:
    from apps_platform.ui.console import ColorPolicy

__all__ = [
    "RENDERERS",
    "RenderedOut",
    "Renderer",
    "get",
    "register",
    "register_defaults",
]

#: Формат рендера: P1 — text/json; ndjson добавляется в P4 (§12.2).
RenderFormat = Literal["text", "json"]


@dataclass(frozen=True)
class RenderedOut:
    """Готовый к записи вывод: два независимых канала (§12.1).

    ``stdout`` — данные/JSON (включая JSON-ошибку), ``stderr`` — человеко-текст
    ошибок. Пустая строка означает «в канал ничего не писать».
    """

    stdout: str = ""
    stderr: str = ""


@runtime_checkable
class Renderer(Protocol):
    """Протокол рендерера: чистый метод ``render`` без side effects (ADR-003)."""

    def render(self, result: object) -> RenderedOut:
        """Отформатировать результат по типу — без print, без I/O."""
        ...


@dataclass(frozen=True)
class _FunctionRenderer:
    """Приспособляет чистую функцию ``fn(result)`` к протоколу ``Renderer``."""

    fn: Callable[[object], RenderedOut]

    def render(self, result: object) -> RenderedOut:
        return self.fn(result)


#: Реестр ``type(result) → Renderer`` (обычный dict; наполняется в T8).
RENDERERS: dict[type, Renderer] = {}


def _as_renderer(renderer: Renderer | Callable[[object], RenderedOut]) -> Renderer:
    if isinstance(renderer, Renderer):
        return renderer
    if callable(renderer):
        return _FunctionRenderer(renderer)
    raise TypeError(f"renderer должен быть callable или иметь render(): {renderer!r}")


def register(result_type: type, renderer: Renderer | Callable[[object], RenderedOut]) -> None:
    """Зарегистрировать рендерер для типа результата.

    Принимает и чистую функцию ``fn(result)``, и объект с методом ``render``.
    Повторная регистрация для того же типа перезаписывает (сборка в T8).
    """
    if not isinstance(result_type, type):
        raise TypeError(f"result_type должен быть типом, получен: {result_type!r}")
    RENDERERS[result_type] = _as_renderer(renderer)


def get(result_type: type) -> Renderer:
    """Рендерер для типа результата.

    Для незарегистрированного типа — ``AssertionError`` с именем типа:
    пропуск регистрации должен падать при сборке, а не в рантайме (§5).
    """
    renderer = RENDERERS.get(result_type)
    if renderer is None:
        raise AssertionError(f"нет рендерера для типа {getattr(result_type, '__name__', result_type)!r}")
    return renderer


def register_defaults(*, fmt: RenderFormat = "text", color_policy: ColorPolicy | None = None) -> None:
    """Зарегистрировать стандартные рендереры ошибок P1 для режима вывода.

    P1 регистрирует только ошибки (``PlatformError``): ``fmt="text"`` → текст в
    stderr (§12.3), ``fmt="json"`` → объект в stdout (§12.2, цвет не
    применяется). Формат выбирается по глобальной опции ``--json``: реестр один
    на запуск, composition root (T8) вызывает функцию один раз; ``color_policy``
    — политика канала stderr, вплетается в текстовый рендерер.
    """
    # Локальные импорты: renderers.text/json зависят от RenderedOut этого модуля.
    from apps_platform.ui.renderers import json as json_renderer
    from apps_platform.ui.renderers import text as text_renderer

    if fmt == "text":
        register(PlatformError, partial(text_renderer.render_error, color_policy=color_policy))
    elif fmt == "json":
        register(PlatformError, json_renderer.render_error)
    else:
        raise ValueError(f"неизвестный формат рендера: {fmt!r} (допустимо: 'text', 'json')")
