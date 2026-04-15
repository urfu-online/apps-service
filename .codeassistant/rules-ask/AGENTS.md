# AGENTS.md – Правила для режима Ask

## Ключевые концепции
- **Service discovery**: автоматическое обнаружение сервисов по манифестам `service.yml` + `docker-compose.yml` в `services/{public,internal}/`
- **Caddy как reverse proxy**: конфиги генерируются из Jinja2-шаблонов (`_core/caddy/templates/`), перезагружаются через API
- **Health checks**: HTTP-проверки каждые 30 секунд; требуют `health_check.endpoint` в манифесте
- **BackupManager**: использует rsync (файлы) и pg_dump (БД), расписания на основе croniter
- **Platform CLI**: изолированный CLI для управления платформой, устанавливается отдельно в `_core/platform-cli/`

## Где искать информацию
- **Документация проекта**: `docs/` (MkDocs), включает архитектуру, руководства, best practices
- **Примеры сервисов**: `services/` (пусто в репозитории, но есть тестовые фикстуры в `_core/master/test-fixtures/services/`)
- **Конфигурация**: `.ops-config.yml` (глобальная), `service.local.yml` (локальные переопределения)
- **Шаблоны Caddy**: `_core/caddy/templates/` – domain.caddy.j2, port.caddy.j2, subfolder.caddy.j2
- **Тестовые фикстуры**: `_core/master/test-fixtures/` – используются в интеграционных тестах

## Архитектурные решения
- **Монорепозиторий**: `_core/master` (основной сервис) и `_core/platform-cli` (CLI) живут вместе, но изолированы
- **Внутренние vs публичные сервисы**: internal не проксируются наружу, только для master service
- **Локальные переопределения**: `service.local.yml` (не коммитится) позволяет переопределять настройки для разработки
- **DinD для тестов**: интеграционные тесты используют Docker-in-Docker для полного цикла развертывания

## Часто задаваемые вопросы
- **Как добавить новый сервис?**: создать директорию в `services/public/` с `service.yml` и `docker-compose.yml`
- **Как настроить health check?**: в `service.yml` указать `health_check: { endpoint: "/health", interval: 30 }`
- **Как работает роутинг?**: Caddy генерирует конфиг на основе `routing` из `service.yml` (domain, subfolder, port)
- **Как запустить тесты?**: `make test` (unit), `make test-cov` (с покрытием), интеграционные тесты запускаются через pytest
- **Как обновить Platform CLI?**: выполнить `update-platform.sh` (скрипт переустанавливает CLI в изолированном venv)