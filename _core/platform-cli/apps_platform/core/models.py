"""Доменные типы platform-cli v2 (§10.4 спеки; скелет дедлайна — ADR-001).

Неизменяемые контракты данных: только frozen dataclass и закрытые enum'ы.
Без валидационной логики, без I/O и без вывода. Единственный владелец
моделей домена; новые типы — через ADR-ревью.
"""

from __future__ import annotations

import time
from dataclasses import InitVar, dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class Visibility(StrEnum):
    """Видимость сервиса: public / internal / core (§5.2, §10.4)."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CORE = "core"


class Routing(StrEnum):
    """Тип маршрутизации сервиса: domain / subfolder / port / none (§5.3)."""

    DOMAIN = "domain"
    SUBFOLDER = "subfolder"
    PORT = "port"
    NONE = "none"


class SectionState(StrEnum):
    """Состояние собранной секции status: complete / partial / unavailable (§8.3)."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class FindingLevel(StrEnum):
    """Уровень Finding: error / warning / note (§10.4)."""

    ERROR = "error"
    WARNING = "warning"
    NOTE = "note"


class ObservationSource(StrEnum):
    """Источник Observation: filesystem / docker / caddy / master / direct_probe (§10.4)."""

    FILESYSTEM = "filesystem"
    DOCKER = "docker"
    CADDY = "caddy"
    MASTER = "master"
    DIRECT_PROBE = "direct_probe"


@dataclass(frozen=True)
class ServiceRef:
    """Доменная ссылка на сервис (Приложение E): имя, каталог, visibility, маршрут.

    Поля:
        name — имя сервиса.
        path — путь к каталогу сервиса (манифест рядом).
        visibility — видимость сервиса.
        routing — тип маршрута из манифеста; None — маршрут ещё не разобран (P2).
    """

    name: str
    path: Path
    visibility: Visibility
    routing: Routing | None = None


@dataclass(frozen=True)
class Observation:
    """Происхождение данных по одному источнику (§10.4).

    Поля:
        source — источник наблюдения.
        observed_at — момент наблюдения (timezone-aware datetime).
        stale — результат устарел относительно порога свежести (§11.3).
        note — причина деградации/устаревания, если есть.
    """

    source: ObservationSource
    observed_at: datetime
    stale: bool = False
    note: str | None = None


@dataclass(frozen=True)
class FixSuggestion:
    """Подсказка исправления Finding (§10.4); замена прежнего плоского fix: str.

    Поля:
        description — что меняет предложенное исправление.
        root_cause — корневая причина, если fix — временное средство; иначе None.
        commands — готовые команды argv-массивами; НЕ исполняются.
        risky — исправление рискованно (mv запущенного сервиса и т.п.).
    """

    description: str
    root_cause: str | None = None
    commands: tuple[tuple[str, ...], ...] = ()
    risky: bool = False


@dataclass(frozen=True)
class Finding:
    """Единственная модель проблем/предупреждений (§10.4).

    Отдельного поля warnings нет: предупреждения — это Finding с
    level=warning.

    Поля:
        level — уровень: error / warning / note.
        check — стабильный id проверки (manifest, visibility-dir и т.п.).
        object — затронутый объект: манифест, контейнер, сеть, маршрут.
        message — человекочитаемый текст (§7.6).
        service — сервис, к которому относится finding; иначе None.
        fix — предложенное исправление; иначе None.
    """

    level: FindingLevel
    check: str
    object: str
    message: str
    service: ServiceRef | None = None
    fix: FixSuggestion | None = None


@dataclass(frozen=True)
class Deadline:
    """Бюджет времени на monotonic-часах (ADR-001; применение — с P2, §8.2).

    Поля:
        budget_s — исходный бюджет в секундах.
        _expires_at — внутренний момент истечения (time.monotonic), не задаётся
            вызывающим: вычисляется из now + budget_s.

    Параметры конструктора:
        budget_s — бюджет в секундах.
        now — точка отсчёта на monotonic-шкале; по умолчанию time.monotonic().
    """

    budget_s: float
    now: InitVar[float | None] = None
    _expires_at: float = field(init=False, repr=False)

    def __post_init__(self, now: float | None) -> None:
        started = time.monotonic() if now is None else now
        object.__setattr__(self, "_expires_at", started + self.budget_s)

    @classmethod
    def after(cls, seconds: float) -> Deadline:
        """Дедлайн, отсчитывающий `seconds` от текущего monotonic-момента."""
        return cls(seconds)

    def remaining(self) -> float:
        """Остаток бюджета в секундах; никогда не опускается ниже 0."""
        return max(0.0, self._expires_at - time.monotonic())

    def expired(self) -> bool:
        """Бюджет исчерпан."""
        return self._expires_at <= time.monotonic()


@dataclass(frozen=True)
class DeadlinePolicy:
    """Политика общего бюджета сбора (§8.2: deadline 2s; скелет ADR-001).

    Поля:
        budget_s — бюджет нового Deadline в секундах (дефолт 2.0).
    """

    budget_s: float = 2.0

    def new_deadline(self) -> Deadline:
        """Новый Deadline на весь бюджет от текущего момента."""
        return Deadline(self.budget_s)
