"""Пакет команд platform-cli: субмодули регистрируются владельцем приложения.

Владельцы:

- **v1** (``backups``, ``services``, ``services_create``, ``services_listing``) —
  регистрация на ``apps_platform.legacy_cli.app`` выполняется явным импортом
  в ``legacy_cli.py``;
- **v2** (``legacy`` — заглушки §7.5) — регистрация через
  ``commands.legacy.register(app)`` из ``apps_platform/cli.py`` (T8).

Пакет намеренно пуст: импорт ``commands.legacy`` (v2) не должен тянуть весь
v1 (``legacy_cli``, docker SDK, ``api_client``) — иначе composition root v2
получает legacy-граф зависимостей при импорте.
"""
