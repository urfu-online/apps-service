"""Слой вывода (presenters) platform-cli v2 — ADR-003, §12 спеки.

Форматирование только здесь: use case возвращает результат или ``PlatformError``,
рендерер (``ui/renderers/``) превращает их в ``RenderedOut`` с раздельными
каналами stdout/stderr, а печатает в потоки только ``cli.py`` (§12.1).
Политика цвета и каналов — ``ui/console.py``. NDJSON и виджеты — P4/P2+.
"""

from __future__ import annotations
