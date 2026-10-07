"""Конфигурация platform-cli: резолвинг корня, ops-конфиг, env-политики, AppConfig (§11.1).

Приоритет разрешения project root (первый найденный выигрывает):

1. ``--project-dir PATH`` — CLI, авторитарный (новый уровень v2);
2. ``OPS_PROJECT_ROOT`` env (dev/CI);
3. маркер ``.ops-root`` вверх от CWD;
4. ``project_root`` из системного конфига (production);
5. CWD (совместимость).

Приоритет настроек: **CLI-флаг > env > user config > ``.ops-config.yml``**.

===========================  ================================================================
Настройка                    Источники (убывание приоритета)
===========================  ================================================================
``root``                     ``--project-dir`` > ``OPS_PROJECT_ROOT`` > маркер > системный > CWD
``ops_config``               ``OPS_CONFIG_PATH`` > ``root/.ops-config.yml`` > системные кандидаты
                             (``.ops-config.local.yml`` deep-merge к найденному файлу)
``master_url``               CLI > ``.ops-config.yml`` > ``http://localhost:8001``
``ssl_verify``               ``PLATFORM_ENV=production`` (принудительно True, выше CLI) >
                             CLI ``--insecure`` > ``PLATFORM_SSL_VERIFY`` > True
``api_token``                только env ``PLATFORM_API_TOKEN`` (никогда не печатается/логируется)
``user_prefs``               CLI > user config (``${XDG_CONFIG_HOME:-~/.config}/platform/config.yml``,
                             только preferences) > дефолты
===========================  ================================================================

В P1 CLI-флагов уровня config ещё нет — приоритет источников зафиксирован в
сигнатуре ``make_app_config`` (``project_dir``/``insecure``/``master_url``/
``user_prefs`` занимают место CLI-уровня).

Ошибки — только ``PlatformError`` из ``core/errors.py``: невалидный
``--project-dir``/``OPS_PROJECT_ROOT`` → ``invalid_value`` (exit 2), отсутствие
ops-конфига → ``config_not_found`` (exit 3). Печати в модуле нет — только
logging; текст ошибки выводит вызывающий слой.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from apps_platform.core.errors import PlatformError

logger = logging.getLogger(__name__)

# Константы
_PROJECT_ROOT_MARKER = ".ops-root"
_DEFAULT_MASTER_URL = "http://localhost:8001"

# Кандидаты системного конфига (приоритет сверху вниз). В production
# используется /etc/ops-manager/config.yml; канонический путь установки /apps
# и per-user конфиг служат fallback'ом для дев-окружения.
_SYSTEM_CONFIG_PATHS = (
    Path("/etc/ops-manager/config.yml"),
    Path("/apps/.ops-config.yml"),
    Path.home() / ".config" / "ops-manager" / "config.yml",
)

# Известные секции status (§8.1) и ключи user config (§8.2) — неизвестные
# игнорируются с warning (в конфиге терпимо, §8.2).
_KNOWN_SECTIONS = frozenset({"services", "health", "problems", "resources", "backups"})
_USER_CONFIG_KEYS = frozenset({"status", "health"})
_STATUS_CONFIG_KEYS = frozenset({"sections", "compact", "deadline"})
_HEALTH_CONFIG_KEYS = frozenset({"stale_after"})


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Рекурсивное слияние словарей конфигурации."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _find_marker_root(start: Path) -> Path | None:
    """Поиск корня проекта вверх от `start` по маркеру `.ops-root`.

    Маркер коммитится в репозиторий и однозначно идентифицирует корень проекта,
    в отличие от `.ops-config.yml`, который может встречаться во вложенных сервисах.
    """
    current = start.resolve()
    for parent in [current, *current.parents]:
        if (parent / _PROJECT_ROOT_MARKER).exists():
            return parent
    return None


def _read_config_file(cfg_path: Path) -> dict[str, Any]:
    """Чтение YAML-конфига с применением .local-переопределения."""
    with open(cfg_path) as f:
        config: dict[str, Any] = yaml.safe_load(f) or {}
    local_override = cfg_path.parent / ".ops-config.local.yml"
    if local_override.exists():
        with open(local_override) as f:
            local_data: dict[str, Any] = yaml.safe_load(f) or {}
        _deep_merge(config, local_data)
    return config


def _system_paths(system_config_paths: Sequence[Path] | None) -> tuple[Path, ...]:
    """Системные кандидаты: явно переданные (legacy/тесты) или модульные."""
    if system_config_paths is None:
        return _SYSTEM_CONFIG_PATHS
    return tuple(system_config_paths)


def resolve_project_root(
    project_dir: Path | None = None,
    *,
    system_config_paths: Sequence[Path] | None = None,
) -> Path:
    """Резолвинг корня проекта по 5 уровням §11.1 (первый найденный выигрывает).

    Уровни:
      1. ``project_dir`` (``--project-dir``, авторитарный): не существует или
         не директория → ``PlatformError(invalid_value)``, exit 2;
      2. ``OPS_PROJECT_ROOT`` env: невалидное значение → ``PlatformError(invalid_value)``
         (текст v1); конверсия в ``typer.Exit`` — на стороне legacy-делегата;
      3. маркер ``.ops-root`` вверх от CWD;
      4. ``project_root`` из системного конфига;
      5. ``Path.cwd()`` — последний рубеж.

    Кэширования нет (fresh на каждый вызов) — ``lru_cache``-семантика v1
    живёт в делегатах ``legacy_cli.get_project_root``. ``system_config_paths``
    подменяет уровень 4 (legacy-патчи и тесты); ``None`` — модульные кандидаты.
    """
    # 1. --project-dir — авторитарный уровень (§11.1): задан и невалиден → ошибка.
    if project_dir is not None:
        root = Path(project_dir)
        if not root.is_dir():
            raise PlatformError(
                code="invalid_value",
                message=f"--project-dir={root} не является существующей директорией.",
                object=str(root),
            )
        logger.debug("PROJECT_ROOT from --project-dir: %s", root)
        return root

    # 2. Явное переопределение через env — авторитарное: если задано, оно обязано
    #    быть валидным. Опечатка/устаревшее значение не должны молча увести CLI
    #    на чужой корень.
    if env_root := os.getenv("OPS_PROJECT_ROOT"):
        root = Path(env_root)
        if root.is_dir():
            logger.debug("PROJECT_ROOT from OPS_PROJECT_ROOT env: %s", root)
            return root
        raise PlatformError(
            code="invalid_value",
            message=(
                f"OPS_PROJECT_ROOT={env_root} не является существующей директорией. "
                "Исправьте переменную или снимите её, чтобы авто-резолвинг сработал."
            ),
            object=env_root,
        )

    # 3. Поиск маркера вверх от текущей директории (dev).
    if marker_root := _find_marker_root(Path.cwd()):
        logger.debug("PROJECT_ROOT from marker %s: %s", _PROJECT_ROOT_MARKER, marker_root)
        return marker_root

    # 4. Значение project_root из системного конфига (production).
    for cfg_path in _system_paths(system_config_paths):
        if not cfg_path.exists():
            continue
        try:
            cfg = _read_config_file(cfg_path)
        except OSError:
            continue
        if pr := cfg.get("project_root"):
            root = Path(pr)
            if root.is_dir():
                logger.debug("PROJECT_ROOT from system config %s: %s", cfg_path, root)
                return root

    # 5. Fallback на текущую директорию.
    logger.debug("PROJECT_ROOT fallback to cwd: %s", Path.cwd())
    return Path.cwd()


def load_ops_config(
    root: Path,
    *,
    system_config_paths: Sequence[Path] | None = None,
) -> dict[str, Any]:
    """Загрузка ops-конфига проекта (fresh, без кэша).

    Кандидаты (первый существующий выигрывает):
      1. ``OPS_CONFIG_PATH`` env — явное переопределение;
      2. ``root/.ops-config.yml`` — source of truth платформы;
      3. системные кандидаты (``/etc/ops-manager``, ``/apps``, per-user).

    Найденный файл читается через ``_read_config_file``: рядом лежащий
    ``.ops-config.local.yml`` deep-merge'ится поверх. Ничего не найдено или
    все кандидаты нечитаемы (OSError) → ``PlatformError(config_not_found)``,
    exit 3, hint из реестра §12.4. ``yaml.YAMLError`` не гасится (как в v1).
    """
    config_candidates: list[Path] = [
        Path(os.getenv("OPS_CONFIG_PATH", root / ".ops-config.yml")),
        *_system_paths(system_config_paths),
    ]
    seen: set[Path] = set()
    for cfg_path in config_candidates:
        cfg_path = Path(cfg_path)
        if cfg_path in seen or not cfg_path.exists():
            continue
        seen.add(cfg_path)
        try:
            return _read_config_file(cfg_path)
        except OSError as e:
            logger.warning("Cannot read config %s: %s", cfg_path, e)

    raise PlatformError(
        code="config_not_found",
        message="Конфиг не найден. Запустите ./install.sh или укажите OPS_CONFIG_PATH",
        object=str(Path(os.getenv("OPS_CONFIG_PATH", root / ".ops-config.yml"))),
    )


def _parse_bool_env(var_name: str, default: bool = True) -> bool:
    """Парсер булевой переменной окружения.

    Поддерживает значения: 1/0, true/false, yes/no, on/off (без учёта регистра).
    """
    raw = os.getenv(var_name)
    if raw is None:
        return default

    value = raw.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _get_ssl_verify(*, insecure: bool) -> bool:
    """Политика TLS-верификации для Master API.

    - В production (PLATFORM_ENV=production) всегда verify=True и флаг --insecure игнорируется
    - В остальных окружениях verify включено по умолчанию (безопасное поведение)
    - Может быть отключено через PLATFORM_SSL_VERIFY=false
    - Флаг --insecure имеет приоритет и отключает верификацию (кроме production)
    """

    platform_env = os.getenv("PLATFORM_ENV", "").strip().lower()
    if platform_env == "production":
        if insecure:
            logger.warning("Ignoring --insecure because PLATFORM_ENV=production")
        return True

    if insecure:
        return False

    return _parse_bool_env("PLATFORM_SSL_VERIFY", default=True)


def _user_config_path() -> Path:
    """Путь user config (§8.2): ``${XDG_CONFIG_HOME:-~/.config}/platform/config.yml``."""
    xdg = os.getenv("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "platform" / "config.yml"


def _parse_duration(value: Any) -> float | None:
    """Парсер длительности user config (``2s``, ``90s`` или число); ``None`` при ошибке."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw.endswith("s"):
            raw = raw[:-1]
        try:
            return float(raw)
        except ValueError:
            return None
    return None


@dataclass(frozen=True)
class UserPrefs:
    """Пользовательские preferences (§8.2): только настройки вывода и таймингов.

    Читаются из user config (не из ``.ops-config.yml`` — тот не дублируется);
    значения по умолчанию совпадают с §8/§11.3.
    """

    sections: tuple[str, ...] = ("services", "health", "problems")
    deadline_s: float = 2.0
    compact: bool = False
    stale_after_s: float = 90.0


def load_user_prefs(path: Path | None = None) -> UserPrefs:
    """Чтение user config §8.2 → ``UserPrefs`` (frozen).

    Файл может отсутствовать — возвращаются дефолты. Неизвестные ключи
    (top-level, внутри ``status``/``health``) и неизвестные секции → warning
    и игнорирование/сохранение как есть («в конфиге терпимо», §8.2). Битый
    YAML/тип → warning и дефолты: preferences не должны ломать CLI.
    """
    cfg_path = path if path is not None else _user_config_path()
    if not cfg_path.is_file():
        return UserPrefs()

    try:
        with open(cfg_path) as f:
            data = yaml.safe_load(f) or {}
    except OSError as e:
        logger.warning("Cannot read user config %s: %s", cfg_path, e)
        return UserPrefs()
    except yaml.YAMLError as e:
        logger.warning("Malformed user config %s: %s", cfg_path, e)
        return UserPrefs()

    if not isinstance(data, dict):
        logger.warning("Ignoring user config %s: top level must be a mapping", cfg_path)
        return UserPrefs()

    unknown = sorted(set(data) - _USER_CONFIG_KEYS)
    if unknown:
        logger.warning("Ignoring unknown keys in %s: %s", cfg_path, ", ".join(unknown))

    status = _section_mapping(data.get("status"), keys=_STATUS_CONFIG_KEYS, name="status", cfg_path=cfg_path)
    health = _section_mapping(data.get("health"), keys=_HEALTH_CONFIG_KEYS, name="health", cfg_path=cfg_path)

    kwargs: dict[str, Any] = {}

    if "sections" in status:
        sections = status["sections"]
        if isinstance(sections, (list, tuple)) and all(isinstance(s, str) for s in sections):
            kwargs["sections"] = tuple(sections)
            unknown_sections = [s for s in kwargs["sections"] if s not in _KNOWN_SECTIONS]
            if unknown_sections:
                logger.warning("Unknown status sections in %s: %s", cfg_path, ", ".join(unknown_sections))
        else:
            logger.warning("Invalid status.sections in %s: expected list of strings", cfg_path)

    if "compact" in status:
        compact = status["compact"]
        if isinstance(compact, bool):
            kwargs["compact"] = compact
        else:
            logger.warning("Invalid status.compact in %s: expected boolean", cfg_path)

    if "deadline" in status:
        deadline = _parse_duration(status["deadline"])
        if deadline is not None:
            kwargs["deadline_s"] = deadline
        else:
            logger.warning("Invalid status.deadline in %s: expected duration like '2s'", cfg_path)

    if "stale_after" in health:
        stale_after = _parse_duration(health["stale_after"])
        if stale_after is not None:
            kwargs["stale_after_s"] = stale_after
        else:
            logger.warning("Invalid health.stale_after in %s: expected duration like '90s'", cfg_path)

    return UserPrefs(**kwargs)


def _section_mapping(value: Any, *, keys: frozenset[str], name: str, cfg_path: Path) -> dict[str, Any]:
    """Извлекает подсловарь user config; не-словарь/неизвестные ключи → warning."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        logger.warning("Ignoring '%s' in %s: expected a mapping", name, cfg_path)
        return {}
    unknown = sorted(set(value) - keys)
    if unknown:
        logger.warning("Ignoring unknown keys in '%s' section of %s: %s", name, cfg_path, ", ".join(unknown))
    return {k: v for k, v in value.items() if k in keys}


@dataclass(frozen=True)
class AppConfig:
    """Собранный конфиг приложения (frozen, ADR-002; §11.1).

    Поля:

    - ``root`` — резолвленный project root;
    - ``ops_config`` — deep-merged ops-конфиг (read-only ``Mapping``);
    - ``master_url`` — URL Master API (дефолт ``http://localhost:8001``);
    - ``ssl_verify`` — политика TLS-верификации (§11.1);
    - ``api_token`` — Bearer-токен Master API, только env; не печатается
      (``repr=False``) и не логируется (§16);
    - ``user_prefs`` — preferences из user config (§8.2).
    """

    root: Path
    ops_config: Mapping[str, Any]
    master_url: str
    ssl_verify: bool
    api_token: str | None = field(repr=False)
    user_prefs: UserPrefs = field(default_factory=UserPrefs)


def make_app_config(
    project_dir: Path | None = None,
    *,
    root: Path | None = None,
    ops_config: Mapping[str, Any] | None = None,
    system_config_paths: Sequence[Path] | None = None,
    insecure: bool = False,
    master_url: str | None = None,
    user_prefs: UserPrefs | None = None,
) -> AppConfig:
    """Сборка ``AppConfig`` по приоритетам §11.1 (CLI > env > user config > ops-конфиг).

    Порядок параметров отражает приоритет: ``project_dir``/``insecure``/
    ``master_url``/``user_prefs`` — место CLI-флагов (в P1 из CLI не передаются);
    env (``OPS_PROJECT_ROOT``/``OPS_CONFIG_PATH``/``PLATFORM_*``) применяется
    внутри резолверов; user config читается следующим; ``.ops-config.yml``
    — источник значений по умолчанию (source of truth платформы).

    Args:
        project_dir: уровень ``--project-dir`` (авторитарный, §11.1).
        root: готовый корень, если уже резолвлен (иначе ``resolve_project_root``).
        ops_config: готовый ops-конфиг (иначе ``load_ops_config``); считается
            уже deep-merged.
        system_config_paths: переопределение системных кандидатов (legacy/тесты).
        insecure: CLI-флаг ``--insecure`` (вне production отключает verify).
        master_url: CLI-override URL Master.
        user_prefs: CLI-override preferences (выше user config).
    """
    resolved_root = (
        root if root is not None else resolve_project_root(project_dir, system_config_paths=system_config_paths)
    )
    cfg = (
        dict(ops_config)
        if ops_config is not None
        else load_ops_config(resolved_root, system_config_paths=system_config_paths)
    )

    resolved_master_url = master_url if master_url is not None else str(cfg.get("master_url") or _DEFAULT_MASTER_URL)

    # Токен — только из env (§11.1/§16): не берётся из конфигов, не логируется.
    api_token = os.getenv("PLATFORM_API_TOKEN") or None

    return AppConfig(
        root=resolved_root,
        ops_config=MappingProxyType(cfg),
        master_url=resolved_master_url,
        ssl_verify=_get_ssl_verify(insecure=insecure),
        api_token=api_token,
        user_prefs=user_prefs if user_prefs is not None else load_user_prefs(),
    )


@lru_cache(maxsize=1)
def get_project_root() -> Path:
    """Совместимая обёртка v1-имени: кэшированный ``resolve_project_root``.

    Кэш — на время процесса (семантика v1); ошибки выходят как
    ``PlatformError`` (конверсия в ``typer.Exit`` — в ``legacy_cli``).
    """
    return resolve_project_root()


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    """Совместимая обёртка v1-имени: кэшированный ``load_ops_config`` по ``get_project_root``."""
    return load_ops_config(get_project_root())
