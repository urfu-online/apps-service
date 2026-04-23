# AGENTS.md – Контекст проекта apps-service-opus

## Стек и окружение
- Python 3.12, FastAPI + NiceGUI (UI), aiodocker для управления контейнерами
- Caddy как reverse proxy с генерацией конфигов из Jinja2-шаблонов
- Монорепозиторий: `_core/master` (основной сервис), `_core/platform-cli` (изолированный CLI)
- Service discovery через сканирование `services/{public,internal}/` с манифестами `service.yml` + `docker-compose.yml`
- Локальные переопределения: `service.local.yml` (не коммитится), `.ops-config.local.yml`

## Команды и инструменты
- `make dev` – запуск через poetry run dev (uvicorn с reload)
- `make test` – pytest с `--asyncio-mode=auto` и покрытием (см. pytest.ini)
- `docker compose` используется через DockerManager (не напрямую)
- Platform CLI (`_core/platform-cli/`) – изолированный venv, устанавливается отдельно

## Стиль кодирования
- Длина строки 120 символов (ruff line-length)
- Ruff категории: E, F, W, I, N, UP, B, C4 (определено в platform-cli)
- В master service ruff не настроен, но рекомендуется придерживаться тех же правил

## Тестирование
- Трехуровневая система: unit → integration → full‑deploy‑cycle
- Асинхронные тесты (pytest-asyncio) с автоматическим режимом
- DinD (Docker-in-Docker) окружение для интеграционных тестов
- Покрытие измеряется автоматически, HTML-отчет в `htmlcov/`

## Gotchas и скрытые зависимости
- Caddy конфиги генерируются из шаблонов в `_core/caddy/templates/`; изменения требуют перезапуска Caddy через API
- Health checks выполняются каждые 30 секунд, но таймауты не настроены в коде
- BackupManager использует rsync/pg_dump, но расписания задаются через croniter
- Все сервисы должны иметь `service.yml` с полем `health_check.endpoint`, иначе проверка не работает
- Внутренние сервисы (internal) не проксируются наружу, только для master service
- Platform CLI не должен быть установлен в глобальном venv проекта – только в изолированном