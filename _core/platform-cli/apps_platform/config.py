"""Конфигурация проекта: резолвинг корня, загрузка YAML-конфигов, SSL-верификация."""

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import typer
import yaml

from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()

# Константы
_PROJECT_ROOT_MARKER = ".ops-root"

_SYSTEM_CONFIG_PATHS = (
    Path("/etc/ops-manager/config.yml"),
    Path("/apps/.ops-config.yml"),
    Path.home() / ".config" / "ops-manager" / "config.yml",
)


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


@lru_cache(maxsize=1)
def get_project_root() -> Path:
    """Резолвинг корня проекта по приоритетной цепочке.

    Порядок разрешения (первый найденный выигрывает):
      1. `OPS_PROJECT_ROOT` env — явное переопределение (dev/CI);
      2. маркер `.ops-root`, ищется вверх от CWD — работа из поддиректорий (dev);
      3. `project_root` из системного конфига — production, единый источник правды;
      4. `Path.cwd()` — последний рубеж (поведение совместимо со старыми версиями).

    Результат кэшируется на время процесса. CLI корректно работает из любой
    директории и для любого пользователя без изменения настроек.
    """
    if env_root := os.getenv("OPS_PROJECT_ROOT"):
        root = Path(env_root)
        if root.is_dir():
            logger.debug("PROJECT_ROOT from OPS_PROJECT_ROOT env: %s", root)
            return root
        console.print(
            f"[red]❌ OPS_PROJECT_ROOT={env_root} не является существующей директорией. "
            "Исправьте переменную или снимите её, чтобы авто-резолвинг сработал.[/red]"
        )
        raise typer.Exit(1)

    if marker_root := _find_marker_root(Path.cwd()):
        logger.debug("PROJECT_ROOT from marker %s: %s", _PROJECT_ROOT_MARKER, marker_root)
        return marker_root

    for cfg_path in _SYSTEM_CONFIG_PATHS:
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

    logger.debug("PROJECT_ROOT fallback to cwd: %s", Path.cwd())
    return Path.cwd()


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    """Загрузка конфигурации — кэшируется на время процесса.

    Порядок поиска конфига:
      1. `OPS_CONFIG_PATH` env — явное переопределение;
      2. `.ops-config.yml` относительно резолвленного корня проекта;
      3. системные кандидаты (`/etc/ops-manager`, `/apps`, per-user).
    """
    root = get_project_root()
    config_candidates: list[Path] = [
        Path(os.getenv("OPS_CONFIG_PATH", root / ".ops-config.yml")),
        *_SYSTEM_CONFIG_PATHS,
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

    console.print("[red]❌ Конфиг не найден. Запустите ./install.sh или укажите OPS_CONFIG_PATH[/red]")
    raise typer.Exit(1)


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
    """Возвращает значение параметра requests.verify.

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
