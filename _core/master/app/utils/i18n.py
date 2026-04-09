"""Утилиты для человеко-читаемого форматирования времени.

Использует библиотеку humanize с русской локалью (ru_RU)
как отраслевой стандарт де-факто для natural time в Python.
"""

from datetime import datetime, timezone
from typing import Optional

import humanize

# Активируем русскую локаль один раз при импорте
humanize.i18n.activate("ru_RU")


def natural_time(dt: datetime) -> str:
    """Возвращает человеко-читаемое время относительно сейчас.

    Примеры: '5 минут назад', '2 часа назад', 'только что'
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return humanize.naturaltime(dt)


def natural_delta(delta) -> str:
    """Возвращает человеко-читаемую длительность.

    Примеры: '5 минут', '2 часа 5 минут', '3 секунды'
    """
    return humanize.naturaldelta(delta)


def format_datetime(dt: datetime, fmt: Optional[str] = None) -> str:
    """Форматирует datetime в строку с русской локалью.

    По умолчанию: '%d %B %Y, %H:%M' → '07 апреля 2026, 14:30'
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    if fmt is None:
        # Русские названия месяцев
        months = {
            'January': 'января', 'February': 'февраля', 'March': 'марта',
            'April': 'апреля', 'May': 'мая', 'June': 'июня',
            'July': 'июля', 'August': 'августа', 'September': 'сентября',
            'October': 'октября', 'November': 'ноября', 'December': 'декабря',
        }
        result = dt.strftime('%d %B %Y, %H:%M')
        for eng, rus in months.items():
            result = result.replace(eng, rus)
        return result

    return dt.strftime(fmt)
