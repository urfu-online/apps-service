"""PlatformError и закрытый реестр кодов ошибок platform-cli v2 (§12.4).

Это **единственный владелец exit-кодов** приложения: ``code → exit → hint``
задаётся таблицей §12.4 спеки, ``exit_code`` вычисляется из реестра по ``code``
и не может быть задан вызывающим. Реестр закрыт: новые коды добавляются только
через ADR-ревью и правку спеки; неизвестный ``code`` падает при построении
ошибки (KeyError/AssertionError), а не молча превращается в ``internal_error``.

Слой: домен (``core/``) — без вывода, без Typer/Rich/docker/requests.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import FrozenInstanceError, dataclass
from types import MappingProxyType
from typing import Final

#: Версия JSON-обёртки ошибок (§12.2): всегда объект с ``schema_version``.
SCHEMA_VERSION: Final[int] = 1


@dataclass(frozen=True)
class ErrorSpec:
    """Запись реестра §12.4: exit-код и hint-шаблон для одного ``code``."""

    exit_code: int
    hint: str | None


# Контекстные переопределения exit (например, master_unavailable = warning вне
# backup, master_incompatible → exit 0 в `info` — §11.2/§12.4) — ответственность
# вызывающих команд (P2+); здесь хранится дефолтный exit из таблицы §12.4.
_REGISTRY_TABLE: dict[str, ErrorSpec] = {
    # Аргументы/конфигурация — exit 2
    "arg_missing": ErrorSpec(2, "передайте … или уберите --no-input"),
    "service_not_found": ErrorSpec(2, "platform service list --json"),
    "service_exists": ErrorSpec(2, "выберите другое имя"),
    "name_invalid": ErrorSpec(2, "правила имени (§13.3)"),
    "port_conflict": ErrorSpec(2, "порт занят: …"),
    "section_unknown": ErrorSpec(2, "допустимые секции"),
    "no_tty": ErrorSpec(2, "операция требует интерактива или --yes/--no-input"),
    "invalid_value": ErrorSpec(2, "допустимые значения"),
    "command_moved": ErrorSpec(2, "platform --help; заглушки будут удалены в v2.1"),
    "snapshot_not_found": ErrorSpec(2, "platform backup list <svc>"),
    "restore_conflict": ErrorSpec(2, "конфликт перезаписи; повторите с --force"),
    # Обязательная зависимость недоступна — exit 3
    "config_not_found": ErrorSpec(3, "запустите ./install.sh или задайте OPS_CONFIG_PATH"),
    "docker_unavailable": ErrorSpec(3, "проверьте docker ps"),
    "master_unavailable": ErrorSpec(3, "platform info"),
    "master_incompatible": ErrorSpec(3, "версии CLI/Master"),
    "environment_mismatch": ErrorSpec(3, "мутации недоступны из контейнера"),
    "lock_busy": ErrorSpec(3, "выполняется другая операция (lock: …); --wait N"),
    # Ошибка выполнения операции — exit 1
    "compose_failed": ErrorSpec(1, "шаг, stderr в панель"),
    "step_failed": ErrorSpec(1, "шаг деплоя, атрибуция"),
    "postcheck_failed": ErrorSpec(1, "сервис запущен, health failing → logs"),
    "internal_error": ErrorSpec(1, "повторите с --verbose и сообщите баг"),
    # Прервано Ctrl-C — exit 130; подсказки нет («—» в §12.4)
    "cancelled": ErrorSpec(130, None),
}

#: Закрытый неизменяемый реестр ``code → exit → hint`` (§12.4).
ERROR_REGISTRY: Final[Mapping[str, ErrorSpec]] = MappingProxyType(_REGISTRY_TABLE)


@dataclass(frozen=True)
class PlatformError(Exception):
    """Ошибка домена: классифицируется по ``code``, exit берётся из реестра.

    Поля (ADR-003, tech spec §5):

    - ``code`` — ключ закрытого реестра (§12.4);
    - ``message`` — человеческий текст (русский, §7.6), отвечает на 4 вопроса §12.3;
    - ``object`` — затронутый объект (сервис, путь, шаг), попадает в JSON;
    - ``hint`` — шаблон из реестра; можно передать конкретный текст взамен;
    - ``cause`` — исходное исключение (для traceback при ``--verbose``).

    ``exit_code`` — свойство из реестра: задать его при построении нельзя.
    Неизвестный ``code`` → KeyError (реестр закрыт, §12.4).

    Класс **заморожен для полей** (``code``/``message``/``object``/``hint``/
    ``cause`` → ``FrozenInstanceError``), но **служебные атрибуты исключения
    разрешены** (``__traceback__``, ``__context__``, ``__cause__``,
    ``__notes__`` и вообще любые dunder-атрибуты): без этого обёртка команд
    Typer ломает выброс — ``contextlib._GeneratorContextManager.__exit__``
    выполняет ``exc.__traceback__ = traceback`` (bpo-27122), и frozen-
    ``__setattr__`` датакласса превращал бы ЛЮБОЙ ``PlatformError`` во
    ``FrozenInstanceError`` наружу (вместо кода из реестра → exit 1
    ``internal_error``). Механика подмены — в
    :func:`_exception_attr_setattr` (датакласс ``frozen=True`` не позволяет
    объявить ``__setattr__`` в теле класса).
    """

    code: str
    message: str
    object: str | None = None
    hint: str | None = None
    cause: BaseException | None = None

    def __post_init__(self) -> None:
        spec = ERROR_REGISTRY[self.code]  # KeyError — защита закрытого реестра
        if self.hint is None:
            object.__setattr__(self, "hint", spec.hint)
        BaseException.__init__(self, self.message)

    @property
    def exit_code(self) -> int:
        """Exit-код из реестра §12.4 по ``code`` (вызывающий задать не может)."""
        return ERROR_REGISTRY[self.code].exit_code

    def to_json(self) -> dict[str, object]:
        """JSON-контракт ошибки (§12.2): объект с ``schema_version`` для stdout."""
        return {
            "schema_version": SCHEMA_VERSION,
            "error": {
                "code": self.code,
                "message": self.message,
                "object": self.object,
                "hint": self.hint,
            },
        }


def _exception_attr_setattr(self: PlatformError, name: str, value: object) -> None:
    """``__setattr__`` :class:`PlatformError`: поля заморожены, dunder — разрешены.

    - имена, начинающиеся и заканчивающиеся на ``__`` (``__traceback__``,
      ``__context__``, ``__cause__``, ``__notes__``…), записываются как есть:
      их выставляют ``contextlib`` (``exc.__traceback__ = traceback`` на выходе
      из ``@contextmanager``-обёртки команд Typer) и сам ``BaseException``
      (``raise … from``, связка ``__context__``);
    - всё остальное — включая поля ``code``/``message``/``object``/``hint``/
      ``cause`` и ``exit_code`` — ``FrozenInstanceError`` (наследник
      ``AttributeError``), т.е. frozen-семантика полей сохраняется.

    Объявить этот метод в теле класса нельзя: ``@dataclass(frozen=True)``
    (Python 3.14) бросает ``TypeError: Cannot overwrite attribute
    __setattr__``, а ``frozen=False`` сломал бы сгенерированный ``__init__``
    (он присваивает поля как ``self.<field> = ...`` и упёрся бы в этот же
    запрет). Поэтому замороженный ``__setattr__`` датакласса подменяется
    сразу после создания класса — см. присвоение ниже. Подклассам, декорируемым
    ``@dataclass(frozen=True)``, нужна та же подмена.
    """
    if name.startswith("__") and name.endswith("__"):
        object.__setattr__(self, name, value)
        return
    raise FrozenInstanceError(f"cannot assign to field {name!r}")


# Подмена ``__setattr__`` замороженного датакласса — см. докстринг функции.
PlatformError.__setattr__ = _exception_attr_setattr


def wrap_unexpected(exc: BaseException) -> PlatformError:
    """Неожиданное исключение → ``internal_error`` (exit 1), ``cause`` = исходное.

    Traceback печатается только при ``--verbose`` (реализует boundary в cli_v2).
    """
    return PlatformError(
        code="internal_error",
        message=f"Непредвиденная ошибка: {type(exc).__name__}: {exc}",
        cause=exc,
    )


def cancelled() -> PlatformError:
    """Ctrl-C → ``cancelled`` (exit 130), ничего не изменено (§12.4)."""
    return PlatformError(
        code="cancelled",
        message="Операция прервана по Ctrl-C; ничего не изменено.",
    )
