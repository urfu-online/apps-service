"""Скрытые заглушки старых плоских команд platform v2 (спека §7.5, F16).

Командная поверхность v2 переразбита по группам (§7.2: ``service``, ``diag``,
``backup``, ``proxy``), старые плоские вызовы (``platform deploy api``) не
сохраняются, но получают скрытые заглушки: в ``platform2 --help`` их нет
(``hidden=True``), а любой старый вызов (cron, runbooks) перехватывается и
падает понятно — ``PlatformError(code="command_moved")`` → exit 2 (§12.4).

Заглушки существуют весь v2.x; удаление — только с мажорной версией (§7.5).
Печатает заглушка ничего: текст ошибки рендерит exception boundary в
``cli.py`` (T8/T9), здесь только исключение. Адаптеры/docker не вызываются.
Бросается сам ``PlatformError`` — его ``__setattr__`` разрешает служебные
атрибуты исключения (``__traceback__`` и т.п.), которые выставляет
contextlib-обёртка команд Typer (см. ``core/errors.py``).

Регистрация — через :func:`register` на приложении composition root, без
глобального состояния (T8/T9 и тесты сами создают ``typer.Typer``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

import typer

from apps_platform.core.errors import PlatformError

#: Маппинг «старое имя → корень новой команды» (§7.2/§7.5), ровно 9 заглушек.
LEGACY_MOVES: Final[dict[str, str]] = {
    "deploy": "service deploy",
    "stop": "service stop",
    "restart": "service restart",
    "logs": "service logs",
    "backup": "backup",
    "new": "service create",
    "list": "service list",
    "reload": "proxy reload",
    "status": "status",
}

#: Субкоманды v2-группы ``backup`` (§7.2). Плоский v1-вызов ``platform backup SVC``
#: соответствует ``platform backup create SVC`` (§7.2 «Было: backup <svc>»).
_BACKUP_SUBCOMMANDS: Final[frozenset[str]] = frozenset({"create", "list", "restore", "delete"})

#: Настройки click: заглушка принимает любой хвост — позиционные аргументы и
#: любые опции — и игнорирует его (незнакомые опции старых вызовов не должны
#: падать на парсинге, а должны попасть в строку «Было: …»).
_STUB_CONTEXT_SETTINGS: Final[dict[str, bool]] = {
    "allow_extra_args": True,
    "ignore_unknown_options": True,
}


def build_moved_message(old_argv: list[str], new_cmd: str) -> str:
    """Сообщение ошибки §7.5 — чистая функция, без typer и без вывода.

    ``old_argv`` — как вызвали (``["deploy", "api"]``, без имени бинарника),
    ``new_cmd`` — новый вызов целиком после ``platform`` (``"service deploy api"``):

    .. code-block:: text

        Команда изменена в platform v2.
        Было: platform deploy api
        Стало: platform service deploy api

    Строка «Подсказка: …» в message **не** дублируется: hint-шаблон
    ``command_moved`` добавляет text-рендерер из реестра §12.4 (иначе в
    stderr выходило бы две подсказки, находка T8 → T9).
    """
    old_call = " ".join(old_argv)
    return "Команда изменена в platform v2.\n" f"Было: platform {old_call}\n" f"Стало: platform {new_cmd}"


def _new_call(old_name: str, rest: list[str]) -> str:
    """Новый вызов: корень из :data:`LEGACY_MOVES` + хвост старого вызова (§7.2).

    Для ``backup`` плоский синтаксис v1 ``platform backup SVC`` без подкоманды
    превращается в ``platform backup create SVC``; уже известная подкоманда
    (``list``/``restore``/…) передаётся без изменений.
    """
    root = LEGACY_MOVES[old_name]
    if old_name == "backup":
        first_positional = next((token for token in rest if not token.startswith("-")), None)
        if first_positional is not None and first_positional not in _BACKUP_SUBCOMMANDS:
            root = f"{root} create"
    if not rest:
        return root
    return f"{root} {' '.join(rest)}"


def _make_stub(old_name: str) -> Callable[[typer.Context], None]:
    """Обработчик одной заглушки: собирает «Было» из ``ctx.args`` и бросает §12.4.

    ``sys.argv`` не используется: под ``CliRunner``/embedding это чужие argv,
    а ``ctx.args`` — ровно тот хвост, который дошёл до команды (глобальные
    опции T8 вырезает до Typer).
    """

    def stub(ctx: typer.Context) -> None:
        rest = list(ctx.args)
        old_argv = [old_name, *rest]
        raise PlatformError(
            code="command_moved",
            message=build_moved_message(old_argv, _new_call(old_name, rest)),
            object=" ".join(old_argv),
        )

    stub.__name__ = f"legacy_{old_name}"
    stub.__doc__ = f"Заглушка: platform {old_name} → platform {_new_call(old_name, [])} (§7.5)."
    return stub


def register(app: typer.Typer) -> None:
    """Регистрирует все 9 заглушек §7.5 на приложении composition root (T8).

    Команды регистрируются со ``hidden=True`` — в ``platform2 --help`` не
    попадают, но перехватывают старые вызовы и падают ``command_moved``
    (exit 2). Вызывать **до** регистрации настоящих команд с теми же именами
    (``status`` в P2, ``backup`` в P4): поздняя регистрация в Typer
    перезаписывает более раннюю.
    """
    for old_name in LEGACY_MOVES:
        app.command(
            name=old_name,
            hidden=True,
            context_settings=dict(_STUB_CONTEXT_SETTINGS),
        )(_make_stub(old_name))
