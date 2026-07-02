"""Пакет команд platform-cli.

Команды регистрируются на ``apps_platform.cli.app`` при импорте модулей
пакета. Чтобы патчи тестов вида ``apps_platform.cli.<helper>`` продолжали
работать, команды обращаются к общим хелперам через ссылку на модуль
``apps_platform.cli`` (``_cli``), а не через прямой ``from ... import``.

Импорт субмодулей здесь обязателен: иначе ``from apps_platform import commands``
загрузит только этот ``__init__`` и ``@app.command``-декораторы не сработают.
"""

from . import backups, services  # noqa: F401
