"""Composition root platform-cli v2 (T8): общие опции, Ctx, boundary, entry.

Слой: внешний CLI-адаптер (tech spec §10.1). Модуль знает конкретные
адаптеры (``sources/``), реестр рендереров (``ui/``) и правила выхода
(exit-коды берёт из закрытого реестра ``core/errors.py``, §12.4). Печатает
только этот модуль: рендереры возвращают ``RenderedOut``, запись в потоки —
здесь (принцип §10.3).

Структура:

1. :class:`GlobalOpts` + :func:`extract_global_opts` — preprocessing argv:
   общие опции §7.4 (``--verbose --json --no-input --yes --no-color
   --project-dir PATH``) вырезаются **в любой позиции** — до и после
   подкоманды; ограничение Click/Typer обходится явно, как требует §7.4.
   Остаток argv уходит в Typer без изменений.
2. :func:`create_app` — фабрика Typer-приложения: help §7.2, скрытые
   заглушки §7.5, никаких v1-команд. ``Ctx`` здесь **не** собирается.
3. :func:`build_ctx` — сборка зависимостей в ``Ctx`` (frozen): конфиг,
   8 адаптеров, ``DeadlinePolicy``, реестр рендереров. Вызывается лениво
   в обработчиках команд, которым нужен контекст → ``platform2 --help`` и
   заглушки работают без ``.ops-config.yml``.
4. :func:`run_app` — exception boundary: ``PlatformError`` → рендер из
   реестра → запись каналов → exit-код из реестра; неожиданное исключение
   → ``wrap_unexpected`` (exit 1, traceback только при ``--verbose``);
   Ctrl-C/EOF → ``cancelled`` (exit 130); ошибки парсинга Typer → exit 2.
5. :func:`_fallback_emit` — минимальный фолбэк-рендер для ошибок, случившихся
   **до сборки реестра** (``main`` огибает весь пайплайн): тот же контракт
   каналов — JSON-ошибка в stdout, текст в stderr.

Каналы (§12.1/§12.2): JSON-ошибка — объект в **stdout**, текст ошибки —
в **stderr**; ``stdout`` рендерера → ``sys.stdout``, ``stderr`` → ``sys.stderr``.
Exit-коды берёт только boundary из реестра §12.4; ``sys.exit`` — только в
entry-обёртке (``[project.scripts]`` / ``raise SystemExit(main())``).
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

import typer

try:  # typer >= 0.16 вендорит click (typer._click); исключения Typer — свои.
    from typer._click.exceptions import ClickException, MissingParameter, UsageError
except ImportError:  # pragma: no cover — старый typer использует внешний click
    from click.exceptions import ClickException, MissingParameter, UsageError

from apps_platform.commands import legacy as legacy_commands
from apps_platform.config import AppConfig, make_app_config
from apps_platform.core.errors import PlatformError, cancelled, wrap_unexpected
from apps_platform.core.models import DeadlinePolicy
from apps_platform.core.ports import (
    CacheStore,
    CaddyReader,
    DockerReader,
    HealthProber,
    Journal,
    LockManager,
    MasterGateway,
    ServiceDiscovery,
)
from apps_platform.ui.console import ColorPolicy
from apps_platform.ui.renderers import RENDERERS, Renderer, register_defaults

__all__ = [
    "Ctx",
    "GlobalOpts",
    "build_ctx",
    "create_app",
    "extract_global_opts",
    "main",
    "run_app",
]

#: Общие булевы опции §7.4: токен → поле :class:`GlobalOpts` (позиция любая).
_BOOL_OPT_TOKENS: Final[dict[str, str]] = {
    "--verbose": "verbose",
    "--json": "json",
    "--no-input": "no_input",
    "--yes": "yes",
    "--no-color": "no_color",
}

#: Общая опция со значением §7.4 (значение поглощается из argv).
_PROJECT_DIR_OPT: Final[str] = "--project-dir"

#: Имя поля ``Ctx`` → порт из закрытого списка 8 (ADR-002; tech spec §4).
_ADAPTER_PORTS: Final[dict[str, type]] = {
    "discovery": ServiceDiscovery,
    "docker": DockerReader,
    "caddy": CaddyReader,
    "master": MasterGateway,
    "prober": HealthProber,
    "locks": LockManager,
    "cache": CacheStore,
    "journal": Journal,
}


@dataclass(frozen=True)
class GlobalOpts:
    """Общие опции всех команд (§7.4), извлечённые до Typer.

    Поля: verbose (logging DEBUG), json (формат вывода/ошибок), no_input
    (запрет prompt'ов), yes (пропуск подтверждений), no_color (отключение
    цвета), project_dir (авторитарный уровень резолвинга корня, §11.1).
    ``--json`` подразумевает ``--no-input`` (§12.5) — выставляется в
    :func:`extract_global_opts`.
    """

    verbose: bool = False
    json: bool = False
    no_input: bool = False
    yes: bool = False
    no_color: bool = False
    project_dir: Path | None = None


def extract_global_opts(argv: list[str]) -> tuple[GlobalOpts, list[str]]:
    """Извлекает общие опции §7.4 из argv — чистая функция, без Typer.

    Предобработка argv (tech spec §6): общие опции работают **в любой
    позиции** (``platform2 --json deploy api`` и ``platform2 deploy api
    --json`` эквивалентны) — ограничение Click/Typer обходится явно (§7.4).

    Вырезаются: ``--verbose``, ``--json``, ``--no-input``, ``--yes``,
    ``--no-color``, ``--project-dir PATH`` и ``--project-dir=PATH``
    (значение поглощается). ``--json`` → ``no_input=True`` (§12.5).

    Не трогает: неизвестные опции и позиционные аргументы — их разбирает
    Typer (неизвестная опция → exit 2). ``--project-dir`` без значения
    остаётся в остатке (Typer сообщит об ошибке). Разделитель ``--`` не
    обрабатывается: в P1 нет позиций, чувствительных к нему.

    Возвращает ``(opts, остаток argv для Typer)``; порядок остатка сохранён.
    """
    verbose = json_out = no_input = yes = no_color = False
    project_dir: Path | None = None
    remainder: list[str] = []

    index = 0
    while index < len(argv):
        token = argv[index]
        flag_field = _BOOL_OPT_TOKENS.get(token)
        if flag_field is not None:
            if flag_field == "verbose":
                verbose = True
            elif flag_field == "json":
                json_out = True
            elif flag_field == "no_input":
                no_input = True
            elif flag_field == "yes":
                yes = True
            else:
                no_color = True
            index += 1
        elif token == _PROJECT_DIR_OPT:
            if index + 1 < len(argv):
                project_dir = Path(argv[index + 1])
                index += 2
            else:
                remainder.append(token)
                index += 1
        elif token.startswith(f"{_PROJECT_DIR_OPT}="):
            project_dir = Path(token.split("=", 1)[1])
            index += 1
        else:
            remainder.append(token)
            index += 1

    opts = GlobalOpts(
        verbose=verbose,
        json=json_out,
        no_input=no_input or json_out,  # --json implies --no-input (§12.5)
        yes=yes,
        no_color=no_color,
        project_dir=project_dir,
    )
    return opts, remainder


@dataclass(frozen=True)
class Ctx:
    """Контекст команды: конфиг + 8 адаптеров + реестр рендереров (ADR-002).

    Frozen (§10.5): собирается один раз в :func:`build_ctx` и передаётся
    явно в каждый use case; тесты подменяют порты через конструктор
    (``adapters=``/``renderers=``), а не патчи имён (принцип §10.6).
    """

    config: AppConfig
    root: Path
    deadline_policy: DeadlinePolicy
    discovery: ServiceDiscovery
    docker: DockerReader
    caddy: CaddyReader
    master: MasterGateway
    prober: HealthProber
    locks: LockManager
    cache: CacheStore
    journal: Journal
    renderers: Mapping[type, Renderer]
    global_opts: GlobalOpts


def _default_adapters() -> dict[str, object]:
    """Конкретные адаптеры из ``sources/`` (единственное место их импорта).

    Ленивый импорт: ``sources/*`` тянут v1 (``legacy_cli``, docker SDK), а
    ``platform2 --help`` и заглушки контекст не используют.
    """
    from apps_platform.sources.cache import CacheAdapter
    from apps_platform.sources.caddy import CaddyAdapter
    from apps_platform.sources.docker import DockerAdapter
    from apps_platform.sources.filesystem import FilesystemDiscovery
    from apps_platform.sources.journal import JournalAdapter
    from apps_platform.sources.locks import LocksManager
    from apps_platform.sources.master import MasterAdapter
    from apps_platform.sources.probe import ProbeAdapter

    return {
        "discovery": FilesystemDiscovery(),
        "docker": DockerAdapter(),
        "caddy": CaddyAdapter(),
        "master": MasterAdapter(),
        "prober": ProbeAdapter(),
        "locks": LocksManager(),
        "cache": CacheAdapter(),
        "journal": JournalAdapter(),
    }


def _ensure_error_registry(opts: GlobalOpts) -> dict[type, Renderer]:
    """Реестр рендереров для формата этого запуска (§12.2/§12.3).

    Формат ошибки известен уже на этапе boundary: общие опции извлекаются
    **до** Typer, поэтому ``--json`` выбирает JSON-рендер даже для ошибок,
    случившихся до сборки ``Ctx`` (например, ``config_not_found``).
    """
    register_defaults(
        fmt="json" if opts.json else "text",
        color_policy=ColorPolicy(no_color=opts.no_color),
    )
    return dict(RENDERERS)


def build_ctx(
    opts: GlobalOpts,
    *,
    renderers: Mapping[type, Renderer] | None = None,
    adapters: Mapping[str, object] | None = None,
    system_config_paths: Sequence[Path] | None = None,
) -> Ctx:
    """Сборка ``Ctx`` — единственный place, знающий concrete adapters (ADR-002).

    Composition root P1: резолвинг корня/ops-конфига идёт через
    ``config.make_app_config`` (§11.1; ``system_config_paths=()`` в тестах
    отключает системных кандидатов), ``DeadlinePolicy`` — из
    ``user_prefs.deadline_s`` (§8.2), реестр рендереров — ``ui/renderers``
    (ошибки P1: text → stderr / json → stdout).

    Вызывается **лениво** — в обработчиках команд, которым нужен контекст,
    а не при импорте/создании app: ``platform2 --help`` и заглушки работают
    без ``.ops-config.yml``.

    Тестовая подмена через конструктор (принцип §10.6, без патчей):

    - ``adapters`` — переопределение адаптеров по именам полей ``Ctx``
      (остальные берутся из ``sources/``); каждое значение обязано
      реализовывать свой порт;
    - ``renderers`` — свой реестр вместо дефолтного.

    Raises:
        AssertionError: неизвестное имя адаптера, адаптер не проходит
            isinstance по порту или в реестре нет рендерера
            ``PlatformError`` (ошибка сборки, а не рантайма, §5).
        PlatformError: ``config_not_found`` (exit 3) и прочие ошибки
            конфигурации из ``config.py``.
    """
    config = make_app_config(opts.project_dir, system_config_paths=system_config_paths)

    active_adapters = _default_adapters()
    if adapters:
        unknown = sorted(set(adapters) - set(_ADAPTER_PORTS))
        if unknown:
            raise AssertionError(f"неизвестные адаптеры: {', '.join(unknown)}; допустимые: {', '.join(_ADAPTER_PORTS)}")
        active_adapters.update(adapters)

    for field_name, port in _ADAPTER_PORTS.items():
        adapter = active_adapters[field_name]
        if not isinstance(adapter, port):
            raise AssertionError(f"адаптер поля {field_name!r} не реализует порт {port.__name__}")

    active_renderers = _ensure_error_registry(opts) if renderers is None else renderers
    if PlatformError not in active_renderers:
        raise AssertionError("нет рендерера для PlatformError: boundary не сможет вывести ошибку (tech spec §5)")

    return Ctx(
        config=config,
        root=config.root,
        deadline_policy=DeadlinePolicy(budget_s=config.user_prefs.deadline_s),
        discovery=cast(ServiceDiscovery, active_adapters["discovery"]),
        docker=cast(DockerReader, active_adapters["docker"]),
        caddy=cast(CaddyReader, active_adapters["caddy"]),
        master=cast(MasterGateway, active_adapters["master"]),
        prober=cast(HealthProber, active_adapters["prober"]),
        locks=cast(LockManager, active_adapters["locks"]),
        cache=cast(CacheStore, active_adapters["cache"]),
        journal=cast(Journal, active_adapters["journal"]),
        renderers=active_renderers,
        global_opts=opts,
    )


def create_app() -> typer.Typer:
    """Фабрика Typer-приложения v2: help §7.2 + заглушки §7.5, без v1-команд.

    ``Ctx`` здесь не собирается (см. :func:`build_ctx`): приложение создаётся
    до извлечения контекста, поэтому ``--help`` и заглушки не читают
    конфигурацию.
    """
    app = typer.Typer(
        name="platform",
        help="Управление платформой: status, info, service, diag, backup, proxy (§7.2).",
        add_completion=False,
        # §7.4: -h эквивалентен --help (T11); Typer 0.26 не принимает
        # help_option_names напрямую — контекстная настройка Click.
        context_settings={"help_option_names": ["-h", "--help"]},
    )
    # Скрытые заглушки старых плоских команд (§7.5) — 9 штук, в help не видны.
    legacy_commands.register(app)
    return app


def _print_traceback(error: PlatformError) -> None:
    """Traceback в stderr — только при ``--verbose`` (§12.3), только stderr.

    Корень цепочки — ``cause`` (если задан, печатается его traceback, включая
    chaining «The above exception…»), иначе сам ``PlatformError``. Если у
    корня нет стека (исключение сконструировано, но не бросалось) — печатать
    нечего, строка его сообщения уже есть в тексте ошибки.
    """
    root = error.cause if error.cause is not None else error
    if root.__traceback__ is None:
        return
    traceback.print_exception(type(root), root, root.__traceback__, file=sys.stderr)


def _emit_error(error: PlatformError, registry: Mapping[type, Renderer], opts: GlobalOpts) -> int:
    """Рендерит ошибку в каналах и возвращает exit-код из реестра §12.4.

    JSON (``--json``) → объект в stdout (§12.2); текст → в stderr (§12.1).
    Traceback — только ``--verbose``, только stderr, через ``cause`` (§12.3);
    для ``cancelled`` (Ctrl-C, exit 130) traceback не печатается никогда —
    прерывание не является инцидентом для отладки (§12.5).
    """
    rendered = registry[PlatformError].render(error)
    if rendered.stdout:
        sys.stdout.write(rendered.stdout)
        sys.stdout.flush()
    if rendered.stderr:
        sys.stderr.write(rendered.stderr)
        sys.stderr.flush()
    if opts.verbose and error.code != "cancelled":
        _print_traceback(error)
    return error.exit_code


def _fallback_emit(error: PlatformError, opts: GlobalOpts) -> int:
    """Минимальный фолбэк-рендер boundary до сборки реестра рендереров (T9).

    ``main`` огибает весь пайплайн (extract → logging → ``create_app`` →
    ``run_app``): если реестр ещё не собран (или его сборка/рендер упала),
    контракт каналов всё равно соблюдается — JSON-ошибка (``--json``) —
    объект ``{schema_version, error}`` в **stdout** (§12.2), текст — в
    **stderr** (§12.1); traceback — только при ``--verbose``. Exit-код —
    по-прежнему из реестра §12.4 (``error.exit_code``).

    Тот же формат, что у рендереров ``ui/renderers/``: первая строка message
    с маркером ``✘``, последующие — с отступом, затем «Объект:»/«Подсказка:».
    """
    if opts.json:
        sys.stdout.write(json.dumps(error.to_json(), ensure_ascii=False) + "\n")
        sys.stdout.flush()
    else:
        message_lines = error.message.splitlines() or [""]
        lines = [f"✘ {message_lines[0]}"]
        lines.extend(f"  {line}" for line in message_lines[1:])
        if error.object is not None:
            lines.append(f"  Объект: {error.object}")
        if error.hint:
            lines.append(f"  Подсказка: {error.hint}")
        sys.stderr.write("\n".join(lines) + "\n")
        sys.stderr.flush()
    if opts.verbose and error.code != "cancelled":
        _print_traceback(error)
    return error.exit_code


def run_app(app: typer.Typer, argv: Sequence[str], opts: GlobalOpts) -> int:
    """Exception boundary: единственное место exit-кодов приложения (T9).

    Вызывает приложение в не-standalone режиме (Typer возвращает код
    ``Exit``/``--help`` вместо ``sys.exit``) и классифицирует исключения:

    - ``PlatformError`` (и его подклассы, в т.ч. заглушки §7.5) → рендер из
      реестра по типу → каналы → ``exit_code`` из реестра §12.4;
    - ошибки парсинга Typer/Click → ``arg_missing``/``invalid_value`` (exit 2);
    - неожиданное исключение → ``wrap_unexpected`` (exit 1; traceback только
      при ``--verbose``);
    - ``Abort``/``KeyboardInterrupt`` → ``cancelled`` (exit 130, без traceback);
      Typer (его переопределённый ``main`` в ``typer.core``) гасит
      ``KeyboardInterrupt`` **внутри** команды и возвращает ``Exit(130)``
      как int-результат — такой результат классифицируется как ``cancelled``
      (иначе Ctrl-C давал бы 130 молча, без сообщения в канал);
    - ``SystemExit`` (EPIPE и подобное) → его код.

    Возвращает exit-код, сам не завершает процесс: ``sys.exit`` вызывает
    только entry-обёртка (``[project.scripts]``/``SystemExit(main())``).
    Никаких ``try/except`` в командах — классификация только здесь.

    Exceptions, случившиеся **до** сборки реестра (в ``_ensure_error_registry``)
    или внутри обработчиков, уходят в fallback-boundary :func:`main`.
    """
    registry = _ensure_error_registry(opts)
    try:
        command = typer.main.get_command(app)
        result = command(args=list(argv), standalone_mode=False)
    except PlatformError as exc:
        return _emit_error(exc, registry, opts)
    except UsageError as exc:
        code = "arg_missing" if isinstance(exc, MissingParameter) else "invalid_value"
        return _emit_error(PlatformError(code=code, message=exc.format_message(), cause=exc), registry, opts)
    except ClickException as exc:
        return _emit_error(wrap_unexpected(exc), registry, opts)
    except (typer.Abort, KeyboardInterrupt):
        return _emit_error(cancelled(), registry, opts)
    except SystemExit as exc:
        exit_code = exc.code
        return exit_code if isinstance(exit_code, int) else (0 if exit_code is None else 1)
    except Exception as exc:
        return _emit_error(wrap_unexpected(exc), registry, opts)

    if isinstance(result, int) and not isinstance(result, bool):
        if result == 130:
            # Typer гасит KeyboardInterrupt внутри команды → Exit(130) как
            # int-результат (см. докстринг): классифицируем как Ctrl-C, чтобы
            # cancelled попал в канал, а не завершился молча (§12.5).
            return _emit_error(cancelled(), registry, opts)
        return result
    return 0


def _configure_logging(*, verbose: bool) -> None:
    """Logging CLI: WARNING по умолчанию, DEBUG при ``--verbose``.

    Уровень root-логгера выставляется явно: ``basicConfig`` — no-op, если
    handlers уже добавлены (pytest, embedding).
    """
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
    logging.getLogger().setLevel(level)
    # Сторонние библиотеки не должны спамить при --verbose.
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    """Точка входа ``platform2`` (``pyproject [project.scripts]``).

    Порядок: извлечь общие опции §7.4 (до Typer — формат ошибок известен) →
    logging по ``--verbose`` → приложение + boundary :func:`run_app`.

    ``main`` — внешний контур boundary: всё, что вышло **из** ``run_app``
    (сборка реестра/приложения, сбой в обработчике ошибки), проходит тот же
    контракт через :func:`_fallback_emit`: ``PlatformError`` → его ``exit_code``,
    ``KeyboardInterrupt``/``Abort`` → ``cancelled`` (130), прочее →
    ``wrap_unexpected`` (1); JSON → stdout, текст → traceback → stderr.

    Возвращает exit-код (console-script обёртка передаёт его в ``sys.exit``).
    """
    raw = list(sys.argv[1:]) if argv is None else list(argv)
    opts = GlobalOpts()  # значение-заглушка, если даже extract упал
    try:
        opts, remainder = extract_global_opts(raw)
        _configure_logging(verbose=opts.verbose)
        return run_app(create_app(), remainder, opts)
    except PlatformError as exc:
        return _fallback_emit(exc, opts)
    except (typer.Abort, KeyboardInterrupt):
        return _fallback_emit(cancelled(), opts)
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) and not isinstance(code, bool) else (0 if code is None else 1)
    except Exception as exc:
        return _fallback_emit(wrap_unexpected(exc), opts)


if __name__ == "__main__":
    raise SystemExit(main())
