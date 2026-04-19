"""Утилиты для работы с Docker SDK.

В проекте периодически используется `docker.from_env()`. Важно закрывать client, чтобы:
- не накапливались открытые сокеты/соединения;
- корректно освобождались ресурсы при исключениях.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import docker


@contextmanager
def docker_client() -> Iterator[Any]:
    """Контекстный менеджер для `docker.from_env()` с гарантированным `close()`."""

    client = docker.from_env()
    try:
        yield client
    finally:
        client.close()

