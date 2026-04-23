# AI Context: apps-service-opus

## 1. Архитектура и стек [АКТУАЛЬНО]

### Компоненты

- **Master Service** (`_core/master/`): FastAPI + NiceGUI, Python 3.12.7 (основная), совместимость с 3.11-3.13
- **Caddy Proxy** (`_core/caddy/`): Reverse proxy с on-demand TLS, Admin API на 127.0.0.1:2019
- **Docker**: Управление контейнерами через aiodocker/docker SDK
- **Service Discovery**: Сканирование `services/{public,internal}/`
- **Keycloak** (опционально): Аутентификация, порт 8080 (если включена)

### Порты

| Сервис      | Порт | Назначение                     | Примечание |
| ----------- | ---- | ------------------------------ | ---------- |
| Master API  | 8000 | REST API                       | Внутри контейнера; наружу пробрасывается через Caddy |
| Master UI   | 8001 | NiceGUI интерфейс              | Проброс host:8001 → container:8000 |
| Caddy HTTP  | 80   | Входящий трафик                | |
| Caddy HTTPS | 443  | TLS трафик                     | |
| Caddy Admin | 2019 | Caddy API (только localhost)   | Проброс 127.0.0.1:2019 → container:2019 |
| Keycloak    | 8080 | Аутентификация (если включена) | |

### Flow деплоя

```
1. ServiceDiscovery.scan_all() → читает service.yml + docker-compose.yml
2. CaddyManager.regenerate_all() → Jinja2 шаблоны → conf.d/*.caddy
3. CaddyManager.reload_caddy() → POST :2019/load или SIGUSR1
4. DockerManager.deploy_service() → docker compose up -d
```

## 2. Конвенции и правила [АКТУАЛЬНО]

### Структура сервисов

```
services/
├── public/           # Доступны извне (домены/поддомены)
└── internal/         # Только внутри Docker сети
    └── {service}/
        ├── service.yml          # Манифест (обязателен)
        ├── docker-compose.yml   # Контейнеры
        └── service.local.yml    # Локальные override (gitignored)
```

### service.yml схема

```yaml
name: string                    # Уникальное имя (slug)
display_name: string            # Человекочитаемое
version: string                 # Версия сервиса
description: string             # Описание (опционально)
type: docker-compose            # docker-compose | docker | static
visibility: internal            # public | internal (по умолчанию internal)
routing:                        # Список маршрутов
  - type: domain                # domain | subfolder | port | auto_subdomain
    domain: example.com         # Для type=domain
    base_domain: apps.urfu.online # Для auto_subdomain/subfolder
    path: /service              # Для type=subfolder
    port: 8080                  # Для type=port
    internal_port: 8000         # Порт контейнера
    container_name: string      # Имя контейнера для прямого проксирования
    strip_prefix: true          # Удалять префикс пути при проксировании
    auto_subdomain: bool        # {name}.base_domain
health:
  enabled: true
  endpoint: /health             # Путь проверки
  interval: 30s
  timeout: 10s
  retries: 3
backup:
  enabled: false
  schedule: "0 2 * * *"         # cron-формат
  retention_days: 30            # Дней хранения (используется для пометки в БД)
  paths: []                     # Пути для бэкапа
  databases: []                 # Конфиг БД
  kopia_policy:                 # Политики хранения в Kopia
    keep-daily: 7
    keep-weekly: 4
    keep-monthly: 6
    keep-annual: 2
  storage_type: filesystem      # filesystem, s3, sftp
tags: []
```

### Именование

- Сервисы: kebab-case (`my-service-name`)
- БД контейнеры: `{service_name}_{db_name}_1`
- Caddy конфиги: `{service_name}.caddy` или `_subfolder_{base_domain}.caddy`
- Бэкапы: `{service_name}_{YYYYMMDD}_{HHMMSS}/`

### Запреты

- НЕ коммитить `service.local.yml` — только в .gitignore
- НЕ редактировать файлы в `conf.d/` руками (генерируются)
- НЕ использовать `..` в путях бэкапа (path traversal check)
- НЕ запускать Docker напрямую — использовать DockerManager

## 3. Карта критических файлов [АКТУАЛЬНО]

| Зона                | Ключевые файлы                                | Назначение                                          |
| ------------------- | --------------------------------------------- | --------------------------------------------------- |
| **Config**          | `_core/master/app/config.py`                  | Pydantic-settings, переменные окружения             |
| **Entry**           | `_core/master/app/main.py`                    | FastAPI lifespan, фоновые задачи, UI pages          |
| **Discovery**       | `_core/master/app/services/discovery.py`      | Сканирование сервисов, watchdog, мёрж конфигов      |
| **Caddy**           | `_core/master/app/services/caddy_manager.py`  | Генерация конфигов из Jinja2, Caddy API reload      |
| **Docker**          | `_core/master/app/services/docker_manager.py` | Docker compose управление, stats, logs              |
| **Health**          | `_core/master/app/services/health_checker.py` | HTTP health checks каждые 30 сек                    |
| **Backup**          | `_core/master/app/services/kopia_backup_manager.py` | Kopia с дедупликацией, шифрованием, политиками хранения |
| **Notifier**        | `_core/master/app/services/notifier.py`       | ntfy.sh/Apprise (поддерживает Telegram, Email, Slack и 50+ сервисов) |
| **TLS API**         | `_core/master/app/api/routes/tls.py`          | On-demand TLS валидация                             |
| **API Routes**      | `_core/master/app/api/routes/*.py`            | services, deployments, logs, backups, health, users |
| **UI Pages**        | `_core/master/app/ui/*_page.py`               | NiceGUI страницы: main, services, logs, backups     |
| **Models**          | `_core/master/app/models/*.py`                | SQLAlchemy: service, deployment, backup, user       |
| **Conftest**        | `_core/master/tests/conftest.py`              | Pytest fixtures: моки Docker, discovery             |
| **Pytest**          | `_core/master/pytest.ini`                     | `--asyncio-mode=auto`, coverage                     |
| **Full Cycle Test** | `infra/test-env/test_full_cycle.sh`           | DinD интеграционные тесты                           |
| **Caddyfile**       | `_core/caddy/Caddyfile`                       | On-demand TLS, Admin API, импорты                   |
| **Templates**       | `_core/caddy/templates/*.caddy.j2`            | Jinja2: domain, subfolder, port, auto_subdomain     |
| **Ops Config**      | `.ops-config.yml`                             | Корневые пути, docker_host                          |
| **Docker Client**   | `_core/master/app/utils/docker_client.py`     | Инициализация Docker клиента                        |

## 4. Ограничения и подводные камни [АКТУАЛЬНО]

### Pytest

- `--asyncio-mode=auto` обязателен — без него async fixtures не работают
- Coverage репорт в `htmlcov/index.html`
- Тесты трёх уровней: unit → integration → full-deploy-cycle (DinD)

### Caddy

- On-demand TLS требует валидацию через `/api/tls/validate`
- Admin API на `127.0.0.1:2019` (только localhost) — без auth внутри Docker сети
- Config reload через POST `/load` или SIGUSR1 fallback
- `conf.d/development.caddy` импортируется только в `APP_ENV=dev`

### Health Checks

- Запускаются каждые 30 секунд из `health_check_loop()` в `main.py`
- Требуют `endpoint` в service.yml — иначе сервис всегда "healthy"
- Таймаут парсится из строки (например, "10s") функцией `_parse_timeout()` в `health_checker.py`

### Backup

- **Kopia** — система резервного копирования с дедупликацией и шифрованием. Репозиторий инициализируется в `_core/kopia/`.
- **Переменные окружения:** `KOPIA_REPOSITORY`, `KOPIA_REPOSITORY_PASSWORD`, `KOPIA_STORAGE_TYPE` (filesystem, s3, sftp).
- **Политики хранения:** управляются через `kopia_policy` в конфигурации сервиса (keep-daily, keep-weekly и т.д.).
- **Уведомления:** отправляются через ntfy.sh/Apprise при успехе/ошибке бэкапа.
- **Старые бэкапы:** локальные бэкапы в `backups/` больше не создаются.

### Service Discovery

- Использует watchdog.observers.Observer — возможны утечки при рестартах
- `_deep_merge()` рекурсивный — списки заменяются целиком
- Local override применяется после основного манифеста

### Docker

- DockerManager использует `docker.from_env()` — требует /var/run/docker.sock
- Контейнеры ищутся по label `platform.service={name}`
- `container_name` в routing для прямого проксирования

### Local Override

- `.gitignore` должен содержать `*.local.yml`
- Проверка через `os.path.basename()` — не `endswith()`

### DinD (Docker-in-Docker)

- Требуется для full-deploy-cycle тестов
- Сеть `platform_network` должна существовать
- Тестовый образ: `infra/test-env/Dockerfile`

## 5. Правила для AI [АКТУАЛЬНО]

### При изменении кода

1. **Сначала читай**: `service.yml` схему в `discovery.py`
2. **Проверяй conftest.py**: есть ли мок для изменяемого сервиса
3. **Запускай тесты**: `make test` или `pytest --asyncio-mode=auto`
4. **Ruff**: строка 120 символов (E, F, W, I, N, UP, B, C4) — в master service ruff не настроен, но рекомендуется придерживаться тех же правил

### При добавлении endpoint

1. Добавить route в `app/api/routes/` или существующий модуль
2. Подключить в `main.py` в список `routers`
3. Добавить тест в `tests/unit/test_*_endpoints.py`
4. Обновить Caddy config если нужен публичный доступ

### При изменении Caddy

1. Шаблоны в `_core/caddy/templates/*.j2`
2. Логика генерации в `caddy_manager.py`
3. Перезагрузка через `reload_caddy()` — не редактировать conf.d/ руками
4. Тест: `test_full_cycle.sh` Test 4

### При изменении моделей

1. SQLAlchemy модели в `app/models/`
2. Pydantic схемы для API — присутствуют в `app/api/routes/*.py` и `app/models/*.py`
3. Создать миграцию — Alembic не настроен (см. plan/9-alembic-migrations.md)
4. Обновить fixtures в `conftest.py`

### Что игнорировать

- `platform-cli/` — отдельный изолированный пакет со своим venv
- `docs/plan/` — плановые задачи, не текущая реализация
- `docs/DOCUMENTATION_*.md` — мета-анализ документации
- Legacy в `.legacy/`

### Где искать информацию

- API endpoints: `app/api/routes/*.py`
- Фоновые задачи: `main.py` → `lifespan()` → `*_loop()`
- UI: `app/ui/*_page.py`
- Конфигурация: `app/config.py`, `.ops-config.yml`
- Тесты: `tests/unit/` (unit), `tests/integration/` (int), `infra/test-env/` (DinD)