# apps-service

Управление сервисами через манифесты. Положил `service.yml` и `docker-compose.yml` — платформа обнаружит сервис, сгенерирует роутинг, начнёт проверять здоровье и бэкапить по расписанию.

## Принцип

Каждый сервис — директория с двумя файлами:

```
services/public/my-app/
  service.yml          # имя, роутинг, health check, backup
  docker-compose.yml   # контейнеры сервиса
```

Master Service при старте:
1. Сканирует `services/public/` и `services/internal/`
2. Читает `service.yml`, мержит с `service.local.yml` если есть
3. Генерирует конфиг Caddy из Jinja2-шаблонов
4. Отправляет конфиг в Caddy через API
5. Запускает HTTP health checks
6. Включает бэкапы по расписанию

File watcher (watchdog) следит за изменениями — изменил манифест, Caddy перегенерировался.

## Компоненты

```
┌─ Caddy (reverse proxy) ──────────────────┐
│  Роутинг: domain / subfolder / port       │
│  SSL, rate limiting, internal_only        │
└──────────────────┬───────────────────────┘
                   │ proxy
┌──────────────────▼───────────────────────┐
│  Master Service (FastAPI + NiceGUI)       │
│                                           │
│  ServiceDiscovery   → сканирует сервисы   │
│  CaddyManager       → генерирует конфиги  │
│  DockerManager      → compose up/down     │
│  HealthChecker      → HTTP probes 30s     │
│  BackupManager      → rsync, pg_dump      │
│  LogManager         → (stub)              │
│  TelegramNotifier   → уведомления         │
│  EventBus           → file watch events   │
└──────────────────┬───────────────────────┘
                   │
    ┌──────────────┴──────────────┐
    ▼                              ▼
 services/public/           services/internal/
   service.yml                service.yml
   docker-compose.yml         docker-compose.yml
```

Два core-контейнера — `master` и `caddy`. Сервисы — отдельные `docker-compose.yml`, каждый на сети `platform_network`.

## Что работает

| Компонент | Статус | Примечание |
|---|---|---|
| ServiceDiscovery | ✅ | Сканирование, local override, file watcher |
| CaddyManager | ✅ | Генерация domain/subfolder/port маршрутов |
| DockerManager | ✅ | deploy/stop/restart для docker-compose |
| HealthChecker | ✅ | HTTP probes с Telegram-уведомлениями |
| BackupManager | ⚠️ | Файлы и БД работают; Restic upload — нет (скрипты удалены) |
| LogManager | ❌ | Заглушка, данные не собираются |
| Monitoring | ❌ | Loki/Prometheus/Grafana — не реализовано |
| Auth (builtin) | ✅ | SQLite + bcrypt |
| Auth (Keycloak) | ⚠️ | Частично: login/token issuance — внешний |
| NiceGUI UI | ⚠️ | Dashboard, сервисы, логи; детальная страница сервиса — редирект |
| Platform CLI | ✅ | 9 команд: list, new, deploy, stop, restart, logs, status, backup, reload |
| API | ✅ | FastAPI, Swagger на `/docs` |

## Быстрый старт

```bash
git clone https://github.com/urfu-online/apps-service.git
cd apps-service
./install.sh
./restart_core.sh --build
```

Добавить сервис — создать `services/public/my-app/service.yml` + `docker-compose.yml`, затем `ops up my-app`.

## Манифест

```yaml
name: my-app
version: "1.0.0"
type: docker-compose
visibility: public

routing:
  - type: domain
    domain: myapp.example.com
    internal_port: 80

health:
  enabled: true
  endpoint: /
  interval: 30s

backup:
  enabled: true
  schedule: "0 2 * * *"
```

## Local override

`service.local.yml` рядом с `service.yml` — мержится поверх, в `.gitignore`. Аналогично `.ops-config.local.yml` для настроек платформы.

## Структура

```
.
├── install.sh                  # установка, генерирует .ops-config.yml
├── restart_core.sh             # docker compose для master + caddy
├── .ops-config.yml             # конфиг платформы (tracked)
├── .ops-config.local.yml       # локальный override (gitignored)
│
├── _core/
│   ├── master/                 # Master Service (FastAPI + NiceGUI)
│   ├── caddy/                  # Caddy reverse proxy
│   ├── backup/                 # Restic backup (контейнер есть, скриптов нет)
│   └── platform-cli/           # Platform CLI (Python/Typer)
│
├── services/                   # сервисы (gitignored)
│   ├── public/
│   └── internal/
│
├── shared/templates/           # шаблоны для platform new
├── docs/                       # документация
└── infra/test-env/             # DinD для тестирования
```

## Документация

- [Установка](docs/getting-started/install.md)
- [Первый сервис](docs/getting-started/first-service.md)
- [CLI и UI](docs/getting-started/cli-ui.md)
- [Управление сервисами](docs/user-guide/services.md)
- [Бэкапы](docs/user-guide/backup.md)
- [Мониторинг](docs/user-guide/monitoring.md)
- [Архитектура](docs/architecture.md)
- [Разработка](docs/development.md)
- [Примеры манифестов](docs/examples.md)

## Roadmap

- [ ] **LogManager** — интеграция с Docker API для сбора логов (сейчас заглушка)
- [ ] **Restic upload** — написать скрипты бэкапа в Restic (сейчас только rsync/pg_dump локально)
- [ ] **Детальная страница сервиса** в UI (сейчас редирект на список)
- [ ] **Backup restore/delete** в UI (сейчас кнопки — заглушки)
- [ ] **Login endpoint** в API (сейчас аутентификация только через внешний Keycloak или прямой SQLite access)
- [ ] **`_deploy_static`** — обработчик для `type: static` (тип объявлен в enum, но не реализован)
- [ ] **`external` service type** — обработчик (тип объявлен в enum, но не реализован)
- [ ] **Loki/Prometheus** — мониторинг (директории `monitoring/` нет)
- [ ] **Alembic** — миграции БД (сейчас `create_all()` при старте)

## Тестирование

```bash
cd _core/master
pytest tests/integration/test_full_deploy_cycle.py -v
```

Подробнее — [docs/development/testing.md](docs/development/testing.md).
