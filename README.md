# apps-service

![Python Version](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue)
![Docker](https://img.shields.io/badge/docker-%3E%3D20.10.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-beta-yellow)

Управление сервисами через манифесты. Положил `service.yml` и `docker-compose.yml` — платформа обнаружит сервис, сгенерирует роутинг, начнёт проверять здоровье и бэкапить по расписанию.

## 📋 Оглавление

- [apps-service](#apps-service)
  - [📋 Оглавление](#-оглавление)
  - [Принцип работы](#принцип-работы)
  - [Компоненты](#компоненты)
  - [Требования к системе](#требования-к-системе)
  - [Быстрый старт](#быстрый-старт)
    - [1. Клонирование и установка](#1-клонирование-и-установка)
    - [2. Запуск core-сервисов](#2-запуск-core-сервисов)
    - [3. Добавление первого сервиса](#3-добавление-первого-сервиса)
    - [4. Деплой сервиса](#4-деплой-сервиса)
  - [Что работает](#что-работает)
    - [⚠️ Важные ограничения](#️-важные-ограничения)
  - [Манифест сервиса](#манифест-сервиса)
  - [Local override](#local-override)
  - [Структура проекта](#структура-проекта)
  - [Документация](#документация)
  - [Частые проблемы](#частые-проблемы)
    - [502 Bad Gateway](#502-bad-gateway)
    - [Health check failures](#health-check-failures)
    - [Caddy не генерирует конфиги](#caddy-не-генерирует-конфиги)
    - [Platform CLI не найден](#platform-cli-не-найден)
  - [Roadmap](#roadmap)
  - [Тестирование](#тестирование)

## Принцип работы

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
│  BackupManager      → Kopia, дедупликация │
│  LogManager         → (stub)              │
│  Notifier           → ntfy.sh/Apprise     │
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

## Требования к системе

- **Docker** ≥ 20.10.0 и **Docker Compose** ≥ 2.0.0
- **Python** 3.12 или 3.13 (для разработки)
- **Git** для клонирования репозитория
- **4 ГБ ОЗУ** минимум, 8 ГБ рекомендуется
- **10 ГБ свободного места** на диске
- Доступ к интернету для загрузки образов Docker

> **Примечание:** На macOS и Windows убедитесь, что Docker Desktop запущен и настроен для использования Linux контейнеров.

## Быстрый старт

### 1. Клонирование и установка

```bash
git clone https://github.com/urfu-online/apps-service.git
cd apps-service
./install.sh
```

Скрипт установки предложит выбрать окружение (local/server) и сгенерирует конфигурационный файл `.ops-config.yml`.

### 2. Запуск core-сервисов

```bash
./restart_core.sh --build
```

Эта команда запустит два основных контейнера:

- **Master Service** (API + UI) на портах 8000 (API) и 8001 (UI)
- **Caddy** (reverse proxy) на портах 80 и 443

### 3. Добавление первого сервиса

Создайте директорию и манифесты:

```bash
mkdir -p services/public/hello-world
```

**services/public/hello-world/service.yml:**

```yaml
name: hello-world
version: "1.0.0"
type: docker-compose
visibility: public

routing:
  - type: domain
    domain: hello.localhost
    internal_port: 80
    container_name: hello-world-web-1 # важно указать имя контейнера

health:
  enabled: true
  endpoint: /
  interval: 30s

backup:
  enabled: false
```

**services/public/hello-world/docker-compose.yml:**

```yaml
version: "3.8"
services:
  web:
    image: nginx:alpine
    container_name: hello-world-web-1
    ports:
      - "8080:80"
    networks:
      - platform_network

networks:
  platform_network:
    external: true
```

### 4. Деплой сервиса

```bash
# Используйте Platform CLI (устанавливается через install.sh)
platform deploy hello-world
```

Или через UI: откройте http://localhost:8001, перейдите в раздел "Сервисы" и нажмите "Деплой".

## Что работает

| Компонент        | Статус | Примечание                                                                     |
| ---------------- | ------ | ------------------------------------------------------------------------------ |
| ServiceDiscovery | ✅     | Сканирование, local override, file watcher                                     |
| CaddyManager     | ✅     | Генерация domain/subfolder/port маршрутов                                      |
| DockerManager    | ✅     | deploy/stop/restart для docker-compose                                         |
| HealthChecker    | ✅     | HTTP probes с уведомлениями через ntfy.sh/Apprise                              |
| BackupManager    | ✅     | Kopia с дедупликацией, шифрованием, поддержкой S3/SFTP                         |
| LogManager       | ❌     | Заглушка, данные не собираются                                                 |
| Monitoring       | ❌     | Loki/Prometheus/Grafana — не реализовано                                       |
| Auth (builtin)   | ✅     | SQLite + bcrypt                                                                |
| Auth (Keycloak)  | ⚠️     | Частично: login/token issuance — внешний                                       |
| NiceGUI UI       | ⚠️     | Dashboard, сервисы, логи; детальная страница сервиса — редирект                |
| Platform CLI     | ✅     | 9 команд: list, new, deploy, stop, restart, logs, status, backup, reload       |
| API              | ✅     | FastAPI, Swagger на `/docs`                                                    |

### ⚠️ Важные ограничения

- **Kopia backup** требует настройки переменных окружения `KOPIA_REPOSITORY` и `KOPIA_REPOSITORY_PASSWORD`. По умолчанию используется локальное хранилище.
- **LogManager** является заглушкой — логи не собираются и не отображаются в UI
- **Monitoring stack** (Loki/Prometheus/Grafana) не установлен — требуется ручная настройка
- **Детальная страница сервиса** в UI перенаправляет на общий список сервисов
- **Alembic миграции** не настроены — изменения моделей БД требуют ручного обновления схемы

## Манифест сервиса

```yaml
name: my-app
version: "1.0.0"
type: docker-compose
visibility: public

routing:
  - type: domain
    domain: myapp.example.com
    internal_port: 80
    container_name: my-app-web-1 # обязательно для прямого проксирования

health:
  enabled: true
  endpoint: /
  interval: 30s
  timeout: 10s
  retries: 3

backup:
  enabled: true
  schedule: "0 2 * * *"
  retention_days: 30
  paths:
    - /data
  databases:
    - type: postgres
      container: db
      database: mydb
  kopia_policy:
    keep-daily: 7
    keep-weekly: 4
    keep-monthly: 6
    keep-annual: 2
  storage_type: filesystem
```

## Local override

`service.local.yml` рядом с `service.yml` — мержится поверх, в `.gitignore`. Аналогично `.ops-config.local.yml` для настроек платформы.

Пример `service.local.yml` для разработки:

```yaml
routing:
  - type: domain
    domain: myapp.localhost
    internal_port: 8080
```

## Структура проекта

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

Полная документация доступна в директории `docs/`:

- [Установка](docs/getting-started/install.md) — подробное руководство по установке
- [Первый сервис](docs/getting-started/first-service.md) — создание и деплой первого сервиса
- [CLI и UI](docs/getting-started/cli-ui.md) — использование Platform CLI и веб-интерфейса
- [Управление сервисами](docs/user-guide/services.md) — полный цикл управления сервисами
- [Бэкапы](docs/user-guide/backup.md) — настройка и управление резервным копированием
- [Мониторинг](docs/user-guide/monitoring.md) — мониторинг здоровья сервисов
- [Архитектура](docs/architecture.md) — архитектурные решения и компоненты
- [Разработка](docs/development/index.md) — руководство для разработчиков
- [Примеры манифестов](docs/examples.md) — готовые примеры service.yml

## Частые проблемы

### 502 Bad Gateway

**Симптом:** При обращении к сервису через прокси Caddy возвращается ошибка 502.

**Причины и решения:**

1. **Контейнер сервиса не запущен** — выполните `platform deploy <имя-сервиса>`
2. **Не указан `container_name` в `service.yml`** — добавьте поле `container_name` с именем основного контейнера
3. **Неправильный `internal_port`** — убедитесь, что порт соответствует порту контейнера
4. **Проблемы с сетью Docker** — проверьте, что сервис и Caddy в одной сети (`platform_network`)

### Health check failures

**Симптом:** Сервис отображается как unhealthy (красный индикатор), хотя контейнер работает.

**Решение:**

- Проверьте `health.endpoint` в `service.yml` — эндпоинт должен возвращать 200 OK
- Увеличьте `health.timeout` если сервис отвечает медленно
- Временно отключите health check: `health.enabled: false`

### Caddy не генерирует конфиги

**Симптом:** Изменения в `service.yml` не применяются, сервис недоступен.

**Решение:**

1. Проверьте логи Master Service: `docker logs _core-master-1 --tail 50`
2. Убедитесь, что файл `service.yml` имеет правильный синтаксис YAML
3. Перезагрузите Caddy вручную: `platform reload caddy`

### Platform CLI не найден

**Симптом:** Команда `platform` не распознается.

**Решение:**

- Убедитесь, что `install.sh` выполнен успешно
- Проверьте, что `~/.local/bin` добавлен в `PATH`
- Или используйте полный путь: `_core/platform-cli/.venv/bin/platform`

Полный список проблем и решений: [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

## Roadmap

Полный бэклог и текущий статус задач — в [GitHub Projects](https://github.com/orgs/urfu-online/projects/5).

| #    | Задача                                  | Статус                                                                                                                         |
| ---- | --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| 1–2  | Баги: deployments.py, docker_manager.py | [→ #13](https://github.com/urfu-online/apps-service/issues/13), [→ #14](https://github.com/urfu-online/apps-service/issues/14) |
| 3    | Login endpoint в API                    | [→ #16](https://github.com/urfu-online/apps-service/issues/16)                                                                 |
| 4–7  | LogManager, Restic, UI stubs            | [→ #17](https://github.com/urfu-online/apps-service/issues/17) – [#20](https://github.com/urfu-online/apps-service/issues/20)  |
| 8–10 | Alembic, monitoring, types              | [→ #21](https://github.com/urfu-online/apps-service/issues/21) – [#22](https://github.com/urfu-online/apps-service/issues/22)  |

Подробное описание каждой задачи — в [docs/plan/](docs/plan/).

## Тестирование

```bash
cd _core/master
make test
```

Или для конкретного интеграционного теста:

```bash
pytest tests/integration/test_full_deploy_cycle.py -v --asyncio-mode=auto
```

Подробнее о тестировании: [docs/development/testing.md](docs/development/testing.md).
