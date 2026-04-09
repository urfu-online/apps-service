# apps-service

Платформа управления сервисами на Docker. Один манифест на сервис — всё остальное автоматически.

## Как это работает

Положите `service.yml` и `docker-compose.yml` в `services/public/my-app/`:

```
services/
  public/
    my-app/
      service.yml          # имя, роутинг, health check, backup
      docker-compose.yml   # контейнеры
```

При запуске Master Service:

1. Сканирует `services/`, читает манифесты
2. Генерирует конфиг Caddy из шаблонов — домен, подпапка или порт
3. Отправляет конфиг в Caddy через API
4. Деплоит контейнеры через Docker Compose
5. Запускает health check каждые 30s
6. Включает бэкапы по расписанию если настроены

Изменили `service.yml` — всё перегенерировалось само. Файловый вотчер работает в реальном времени.

## Архитектура

```
Caddy (reverse proxy, SSL)
  │
  │ proxy
  ▼
Master Service ──────────┐
  FastAPI + NiceGUI       │
  ├─ ServiceDiscovery     │ file watch
  ├─ CaddyManager         │── generates .caddy configs
  ├─ DockerManager        │── docker compose up/down
  ├─ HealthChecker        │── HTTP probes every 30s
  ├─ BackupManager        │── restic + pg_dump/mysqldump
  └─ LogManager           │── container logs
                          │
    services/public/      │
    services/internal/    │◄── service.yml + docker-compose.yml
```

Два core-контейнера — `master` и `caddy`. Сервисы — сколько угодно, каждый со своим `docker-compose.yml`. Всё на одной docker сети `platform_network`.

## Установка

```bash
git clone https://github.com/urfu-online/apps-service.git
cd apps-service
./install.sh
```

Скрипт создаст `.ops-config.yml` и установит CLI `ops`.

## Использование

```bash
# Добавить сервис
mkdir -p services/public/my-app
# положить service.yml + docker-compose.yml

# Запустить core
./restart_core.sh --build

# Запустить сервис
ops up my-app

# Посмотреть что работает
ops list
```

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

Ничего лишнего. Платформа берёт из манифеста имя, маршрут, параметры health check и расписание бэкапов. Остальное — в `docker-compose.yml`, как обычно.

## Local override

Для разработки — `service.local.yml` рядом с `service.yml`. Мержится поверх, в `.gitignore` не коммитится. Меняет только то, что отличается — порт, интервал проверок, что угодно.

Аналогично — `.ops-config.local.yml` для настроек платформы.

## Структура

```
.
├── install.sh                  # установка, генерирует .ops-config.yml
├── restart_core.sh             # docker compose для master + caddy
├── .ops-config.yml             # конфиг (tracked, серверные значения)
├── .ops-config.local.yml       # локальный override (gitignored)
│
├── _core/
│   ├── master/                 # Master Service — FastAPI + NiceGUI
│   ├── caddy/                  # Caddy reverse proxy
│   ├── backup/                 # Restic backup
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
- [Управление сервисами](docs/user-guide/services.md)
- [Бэкапы](docs/user-guide/backup.md)
- [Мониторинг](docs/user-guide/monitoring.md)
- [Архитектура](docs/architecture.md)
- [Разработка](docs/development.md)
- [Примеры манифестов](docs/examples.md)

Полная документация — [MkDocs сайт](https://urfu-online.github.io/apps-service/) (собирается `mkdocs build`).

## Тестирование

```bash
cd _core/master
pytest tests/integration/test_full_deploy_cycle.py -v
```

Подробнее — [docs/development/testing.md](docs/development/testing.md).
