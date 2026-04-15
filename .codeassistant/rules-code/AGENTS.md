# AGENTS.md – Правила для режима Code

## Стиль кодирования
- Длина строки 120 символов (ruff line-length)
- Ruff категории: E, F, W, I, N, UP, B, C4 (определено в platform-cli)
- В master service ruff не настроен, но рекомендуется придерживаться тех же правил
- Используйте `poetry run` для запуска скриптов

## Команды разработки
- `make dev` – запуск приложения в режиме разработки (uvicorn с reload)
- `make test` – запуск тестов с параметрами `--asyncio-mode=auto` и покрытием
- `make test-cov` – тесты с детальным отчетом о покрытии
- `docker compose` используется через DockerManager (не напрямую)

## Структура проекта
- Монорепозиторий: `_core/master` – основной сервис, `_core/platform-cli` – изолированный CLI
- Service discovery: сканирует `services/{public,internal}/` с манифестами `service.yml` + `docker-compose.yml`
- Локальные переопределения: `service.local.yml` (не коммитится), `.ops-config.local.yml`

## Gotchas при написании кода
- Caddy конфиги генерируются из шаблонов в `_core/caddy/templates/`; изменения требуют перезапуска Caddy через API
- Health checks выполняются каждые 30 секунд, но таймауты не настроены в коде
- BackupManager использует rsync/pg_dump, расписания задаются через croniter
- Все сервисы должны иметь `service.yml` с полем `health_check.endpoint`, иначе проверка не работает
- Внутренние сервисы (internal) не проксируются наружу, только для master service
- Platform CLI не должен быть установлен в глобальном venv проекта – только в изолированном

## Тестирование
- Трехуровневая система: unit → integration → full‑deploy‑cycle
- Асинхронные тесты (pytest-asyncio) с автоматическим режимом
- DinD (Docker-in-Docker) окружение для интеграционных тестов
- Покрытие измеряется автоматически, HTML-отчет в `htmlcov/`