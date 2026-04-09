# Документация

## Начало работы

- [Установка](getting-started/install.md) — `./install.sh`, что происходит
- [Первый сервис](getting-started/first-service.md) — service.yml + docker-compose.yml
- [CLI и UI](getting-started/cli-ui.md) — ops, platform, NiceGUI

## Пользователю

- [Управление сервисами](user-guide/services.md) — создание, деплой, роутинг
- [Бэкапы](user-guide/backup.md) — rsync, pg_dump, расписание; Restic — не реализован
- [Мониторинг](user-guide/monitoring.md) — health checks, логи через Docker API; Loki/Prometheus — не реализовано

## Разработчику

- [Руководство](development.md) — Poetry, Docker, Makefile
- [Тестирование](development/testing.md) — 3 уровня, mocks, DinD

## Справочник

- [Архитектура](architecture.md) — компоненты, потоки данных, стек
- [API](api.md) — эндпоинты, аутентификация
- [Примеры](examples.md) — манифесты для разных типов сервисов
- [Лучшие практики](best-practices.md) — структура, безопасность

## Статус реализации

| Компонент | Готово |
|---|---|
| ServiceDiscovery, CaddyManager, DockerManager | ✅ |
| Health checks, Telegram-уведомления | ✅ |
| NiceGUI UI (dashboard, сервисы, логи) | ✅ |
| Platform CLI (9 команд) | ✅ |
| API (services, deployments, health, users) | ✅ |
| Бэкапы файлов и БД (rsync, pg_dump) | ✅ |
| Бэкапы в Restic | ❌ Скрипты не написаны |
| LogManager (сбор логов) | ❌ Заглушка |
| Loki / Prometheus / Grafana | ❌ Не начато |
| Страница сервиса в UI | ❌ Редирект |
| Backup restore/delete в UI | ❌ Заглушки |
| Login endpoint в API | ❌ Нет |
| Миграции БД (Alembic) | ❌ `create_all()` |
