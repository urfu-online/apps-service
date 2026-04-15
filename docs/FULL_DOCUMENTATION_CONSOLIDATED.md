# Apps Service Opus — Полная документация (консолидированная)

> **Дата сборки:** 2026-04-16
> **Источник:** /projects/apps-service-opus/docs/
> **Цель:** Консолидированный файл для передачи контекста другому ИИ

---

## Содержание

1. [Обзор проекта (из README)](#1-обзор-проекта)
2. [Архитектура](#2-архитектура)
3. [API](#3-api)
4. [Начало работы](#4-начало-работы)
5. [Руководство пользователя](#5-руководство-пользователя)
6. [Разработка](#6-разработка)
7. [План задач](#7-план-задач)
8. [Устаревшая/противоречивая информация](#8-устаревшаяпротиворечивая-информация)

---

## 1. Обзор проекта

### Принцип работы

Платформа управления сервисами через манифесты. Каждый сервис — директория с двумя файлами:
- `service.yml` — имя, роутинг, health check, backup
- `docker-compose.yml` — контейнеры сервиса

Master Service при старте:
1. Сканирует `services/public/` и `services/internal/`
2. Читает `service.yml`, мержит с `service.local.yml` если есть
3. Генерирует конфиг Caddy из Jinja2-шаблонов
4. Отправляет конфиг в Caddy через API
5. Запускает HTTP health checks
6. Включает бэкапы по расписанию

### Статус компонентов

| Компонент | Статус | Примечание |
|---|---|---|
| ServiceDiscovery | ✅ | Сканирование, local override, file watcher |
| CaddyManager | ✅ | Генерация domain/subfolder/port маршрутов |
| DockerManager | ✅ | deploy/stop/restart для docker-compose |
| HealthChecker | ✅ | HTTP probes каждые 30s, Telegram-уведомления |
| BackupManager | ⚠️ | Файлы и БД работают; Restic upload — нет |
| LogManager | ❌ | Заглушка, данные не собираются |
| Monitoring | ❌ | Loki/Prometheus/Grafana — не реализовано |
| Auth (builtin) | ✅ | SQLite + bcrypt |
| Auth (Keycloak) | ⚠️ | Частично: login/token issuance — внешний |
| NiceGUI UI | ⚠️ | Dashboard, сервисы, логи; детальная страница — редирект |
| Platform CLI | ✅ | 9 команд: list, new, deploy, stop, restart, logs, status, backup, reload |
| API | ✅ | FastAPI, Swagger на `/docs` |

### Структура проекта

```
.
├── install.sh                  # установка, генерирует .ops-config.yml
├── restart_core.sh             # docker compose для master + caddy
├── .ops-config.yml             # конфиг платформы (tracked)
├── .ops-config.local.yml       # локальный override (gitignored)
├── _core/
│   ├── master/                 # Master Service (FastAPI + NiceGUI)
│   ├── caddy/                  # Caddy reverse proxy
│   ├── backup/                 # Restic backup (контейнер есть, скриптов нет)
│   └── platform-cli/           # Platform CLI (Python/Typer)
├── services/                   # сервисы (gitignored)
│   ├── public/
│   └── internal/
├── shared/templates/           # шаблоны для platform new
└── docs/                       # документация
```

---

## 2. Архитектура

### Компоненты

**Master Service** — центральный сервис управления (FastAPI + NiceGUI):
- API (FastAPI)
- Web UI (NiceGUI)
- ServiceDiscovery — сканирование сервисов
- DockerManager — deploy/stop/restart
- CaddyManager — генерация конфигов
- BackupManager — через Restic (частично)
- LogManager — заглушка
- TelegramNotifier — уведомления

**Caddy Proxy** — обратный прокси:
- SSL/TLS терминация (Let's Encrypt)
- Маршрутизация трафика
- Аутентификация через Keycloak
- Rate limiting, защита от DDoS
- Динамическая конфигурация через API

**Restic** — инструмент для бэкапов (скрипты отсутствуют)

### Потоки данных

1. Пользователь → Master Service (UI или API)
2. Master Service сканирует `services/` и обнаруживает изменения
3. Генерирует Caddy-конфиг → отправляет через API Caddy
4. Управляет Docker-контейнерами через Docker SDK
5. Запускает бэкапы через Restic
6. Отправляет уведомления в Telegram

### Технологии

| Компонент | Технология |
|-----------|------------|
| Backend | Python, FastAPI |
| Frontend | NiceGUI |
| Proxy | Caddy (with API) |
| Auth | Keycloak / Builtin (SQLite) |
| Backup | Restic (частично) |
| Orchestration | Docker + Docker Compose |
| DB | SQLite (master.db) |
| Templating | Jinja2 |

---

## 3. API

### Базовый URL

```
http://localhost:8000/api
```

### ⚠️ Аутентификация

**ВНИМАНИЕ:** Все эндпоинты требуют `Authorization: Bearer <token>`.
**Login endpoint в API отсутствует.** Токен получается через внешний Keycloak.

### Основные эндпоинты

#### GET /services
Получение списка сервисов

#### GET /services/{service_name}
Детальная информация о сервисе

#### POST /services/{service_name}/deploy
Деплой/редеплой сервиса

Тело запроса:
```json
{
  "build": true,
  "pull": false
}
```

#### POST /services/{service_name}/stop
Остановка сервиса

#### POST /services/{service_name}/restart
Перезапуск сервиса

#### GET /logs/service/{service_name}
Получение логов сервиса

#### GET /health
Проверка состояния платформы

---

## 4. Начало работы

### Установка

```bash
./install.sh
```

Скрипт задаёт три вопроса:
1. Тип окружения (Local/Server/Custom)
2. Путь к сервисам
3. Куда установить CLI

Создаёт:
- `.ops-config.yml` — конфиг платформы
- `.ops-config.local.yml` — локальный override

### Первый сервис

```bash
# Быстрый способ
platform new my-app public

# Деплой
./restart_core.sh --build
platform deploy my-app
```

Минимальный `service.yml`:
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
```

Минимальный `docker-compose.yml`:
```yaml
version: '3.8'

services:
  my-app:
    image: nginx:alpine
    container_name: my-app
    networks:
      - platform_network

networks:
  platform_network:
    external: true
    name: platform_network
```

### Local override

`service.local.yml` рядом с `service.yml` — мержится поверх, в `.gitignore`.

### CLI и UI

**Platform CLI** (9 команд):
- `platform list` — список сервисов
- `platform new <name> [public|internal]` — создать сервис
- `platform deploy <svc> [--build] [--pull]` — деплой
- `platform stop <svc>` — остановка
- `platform restart <svc>` — перезапуск
- `platform logs <svc> [-f] [-n N]` — логи
- `platform status [<svc>]` — статус + метрики
- `platform backup <svc>` — бэкап
- `platform reload` — перезагрузить Caddy

**Веб-интерфейс (NiceGUI)**:
- Порт 8001
- Страницы: главная, сервисы, логи, бэкапы
- Детальная страница сервиса — редирект на `/services`

---

## 5. Руководство пользователя

### Управление сервисами

#### Структура манифеста service.yml

```yaml
# МЕТАДАННЫЕ
name: my-service
display_name: "Мой Сервис"
version: "1.0.0"
description: "Описание"
type: docker-compose  # docker-compose | docker | static | external
visibility: public    # public | internal

# МАРШРУТИЗАЦИЯ
routing:
  - type: domain
    domain: myservice.example.com
    internal_port: 8000
    container_name: my-service  # ⚠️ ОБЯЗАТЕЛЬНО

# HEALTH CHECK
health:
  enabled: true
  endpoint: /health
  interval: 30s

# БЭКАПЫ
backup:
  enabled: true
  schedule: "0 2 * * *"
  retention: 7
  paths:
    - ./data
  databases:
    - type: postgres
      container: db
      database: myservice
```

#### ⚠️ Критически важно: container_name

**Без `container_name` Caddy проксирует на `host.docker.internal:<port>` — на хост-машину.**
Это legacy-режим: обход SSL, auth, rate limit; конфликты портов; дырка в безопасности.
**Указывайте `container_name` всегда.** Имя должно совпадать с контейнером в `docker-compose.yml`.

#### Типы маршрутизации

1. **domain** — отдельный домен
   ```yaml
   routing:
     - type: domain
       domain: myservice.example.com
       internal_port: 8000
   ```

2. **subfolder** — подпапка
   ```yaml
   routing:
     - type: subfolder
       base_domain: apps.example.com
       path: /my-service
       strip_prefix: true
   ```

3. **port** — прямой порт
   ```yaml
   routing:
     - type: port
       port: 8081
       internal_port: 8000
   ```

### Бэкапы

**Статус:** Бэкапы файлов (rsync) и БД (pg_dump/mysqldump) работают. Restic upload **не реализован**.

**Конфигурация:**
```yaml
backup:
  enabled: true
  schedule: "0 2 * * *"  # cron формат
  retention: 7
  paths:
    - ./data
    - ./uploads
  databases:
    - type: postgres
      container: db
      database: myservice
```

**Ручной бэкап:**
```bash
platform backup my-service
```

**⚠️ Восстановление из бэкапа:** В UI — заглушка «Функция в разработке». API эндпоинты есть, но не реализованы.

### Мониторинг

**Статус:**
- ✅ Health checks — работают (HTTP probes каждые 30s)
- ✅ Логи через Docker API — работают
- ✅ Telegram-уведомления — работают
- ✅ NiceGUI dashboard — работает
- ❌ Loki — не реализован
- ❌ Prometheus/Grafana — не реализовано

**Настройка health check:**
```yaml
health:
  enabled: true
  endpoint: /health
  interval: 30s
  timeout: 10s
  retries: 3
```

**Telegram уведомления:**
```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_IDS=chat_id1,chat_id2
```

---

## 6. Разработка

### Master Service

**Структура:**
```
_core/master/
├── app/
│   ├── api/routes/         # REST API
│   ├── core/               # БД, события, безопасность
│   ├── models/             # SQLAlchemy модели
│   ├── services/           # Бизнес-логика
│   │   ├── discovery.py    # ServiceDiscovery
│   │   ├── caddy_manager.py# Генерация Caddy конфигов
│   │   ├── docker_manager.py
│   │   ├── health_checker.py
│   │   ├── backup_manager.py
│   │   └── log_manager.py  # Заглушка
│   └── ui/                 # NiceGUI интерфейс
├── tests/
│   ├── unit/
│   └── integration/
└── pyproject.toml
```

**Команды:**
```bash
cd _core/master
make test           # pytest
make test-cov       # с покрытием
make test-html      # HTML-отчёт
```

### Тестирование

**Три уровня:**

1. **Level 1: Интеграционные тесты** (~10 сек)
   ```bash
   pytest tests/integration/test_full_deploy_cycle.py -v
   ```

2. **Level 2: Dry-run режим** (~30 сек)
   - Полный цикл без реального деплоя

3. **Level 3: DinD VM** (~5 мин)
   ```bash
   cd infra/test-env
   docker compose up -d
   docker compose exec test-env bash
   ./test_full_cycle.sh
   ```

### Работа с задачами

**Два источника:**
- GitHub Issues — бэклог, приоритизация
- docs/plan/ — архитектурные решения, подзадачи

**Структура docs/plan/:**
```
docs/plan/
  README.md              # обзор всех задач
  N-название.md          # описание задачи
  N-название/            # материалы (логи, скриншоты)
```

**Жизненный цикл:**
1. Создать GitHub Issue
2. AI анализирует → присваивает labels
3. Создать бранч `issue/N-название`
4. Для сложных задач создать `docs/plan/N-название.md`
5. Работать, коммитить
6. По завершении — комментарий к Issue, обновить статус в README.md

### Процесс выпуска релиза

**Чеклист:**
1. Проверка зависимостей — `poetry lock --no-update`
2. Запуск тестов — все 3 уровня
3. Проверка документации — `mkdocs serve`
4. Проверка стиля — `ruff check . --fix`
5. DinD окружение — полный цикл
6. Создание тега — `git tag -a v1.2.0`
7. Обновление CHANGELOG.md
8. Создание релиза на GitHub

### Обновление платформы на сервере

**Чеклист перед обновлением:**
- [ ] Бэкап БД сделан
- [ ] Бэкап сервисов сделан
- [ ] Бэкап Caddy конфига сделан
- [ ] Список сервисов записан
- [ ] Есть план отката

**Процесс:**
```bash
# 1. Бэкап
sudo docker compose -f _core/master/docker-compose.yml down
sudo cp _core/master/master.db /tmp/master.db.backup.$(date +%Y%m%d)
sudo tar czf /tmp/services-backup.$(date +%Y%m%d).tgz services/

# 2. Pull
git pull origin main

# 3. Перезапуск
./restart_core.sh --build

# 4. Проверка
curl -s http://localhost:8001/healthz
platform list
```

---

## 7. План задач

### Актуальный бэклог

| # | Задача | Приоритет | Статус |
|---|--------|-----------|--------|
| 1 | Баги: deployments.py, docker_manager.py | 🔴 Критично | ⬜ |
| 2 | pull/build результаты не проверяются | 🔴 Критично | ⬜ |
| 3 | Login endpoint в API | 🔴 Критично | ⬜ |
| 4 | LogManager — заглушка | 🟠 Средний | ⬜ |
| 5 | Restic upload — скрипты отсутствуют | 🟠 Средний | ⬜ |
| 6 | Детальная страница сервиса в UI | 🟡 Низкий | ⬜ |
| 7 | Backup restore/delete в UI | 🟡 Низкий | ⬜ |
| 8 | static/external service type | 🟡 Низкий | ⬜ |
| 9 | Alembic миграции | 🟠 Средний | ⬜ |
| 10 | Monitoring stack | ⚪ Отложить | ⬜ |
| 11 | Caddy integration аудит | 🔴 Критично | ⬜ |
| 11a | Аудит кода Caddy integration | 🔴 Критично | ⬜ |
| 11b | Аудит реальных сервисов | 🟠 Средний | ⬜ |
| 11c | Тестирование сценариев | 🔴 Критично | ⬜ |
| 11d | Валидация конфигурации | 🟠 Средний | ⬜ |
| 11e | Обновить документацию | 🟡 Низкий | ⬜ |
| 11f | Ограничить legacy-режим | 🟠 Средний | ⬜ |

### Ключевые проблемы

**Баги в deployments.py и docker_manager.py:**
1. `get_service_by_id` не существует — надо использовать `get_service(name)`
2. `ServiceManifest` не имеет поля `id` — есть только `name`
3. Pull/build результаты не проверяются — если pull упал, но up succeeded, деплой считается успешным

**Login endpoint:**
- Все API эндпоинты защищены `Depends(get_current_user)`
- Способов получить токен через API — нет
- Builtin auth: «токен» = `str(user_id)`, небезопасно
- Нет `/login`, `/token`, `/auth` endpoint'ов

**Caddy integration:**
- Документация противоречит коду (примеры без `container_name`)
- Нет защиты от неправильной конфигурации
- Непонятно что происходит когда `container_name` не указан

---

## 8. Устаревшая/противоречивая информация

### ⚠️ Критические несоответствия

1. **Примеры без `container_name`**
   - В `docs/examples.md` и `docs/getting-started/first-service.md` многие примеры не содержат `container_name`
   - Без этого поля Caddy использует `host.docker.internal` — это legacy-режим с проблемами безопасности
   - Исправление: добавить `container_name` во ВСЕ примеры

2. **LogManager — заглушка, но документация описывает Loki**
   - В `docs/user-guide/monitoring.md` описана интеграция с Loki
   - В коде `log_manager.py` — заглушка с in-memory `deque`
   - Логи читаются напрямую из Docker API, минуя LogManager

3. **Restic upload не реализован**
   - В документации описана интеграция с Restic для загрузки бэкапов
   - В коде `_upload_to_restic()` ссылается на несуществующий скрипт
   - Работают только rsync и pg_dump

4. **static/external service types не реализованы**
   - В `service.yml` можно указать `type: static` или `type: external`
   - Обработчики деплоя для них не написаны
   - Может вызвать `AttributeError` или `NameError`

5. **Monitoring stack (Loki/Prometheus/Grafana)**
   - В документации описан полный стек мониторинга
   - Директория `_core/monitoring/` удалена
   - Работают только health checks и Docker API логи

6. **Backup restore в UI**
   - В документации описано восстановление через UI
   - В коде — заглушка «Функция в разработке»

7. **API login endpoint**
   - Документация API предполагает наличие токена
   - Нет endpoint'а для получения токена
   - Нужно использовать внешний Keycloak

8. **Alembic миграции**
   - В коде используется `create_all()` при каждом старте
   - Миграций нет, изменение модели требует ручного пересоздания БД

---

## Итоговый чеклист для нового ИИ

Если ты получил этот файл, вот ключевые моменты:

1. **Стек:** Python 3.12, FastAPI + NiceGUI, Caddy, Docker
2. **Критический баг:** `container_name` обязателен в `service.yml`, но многие примеры его не содержат
3. **Нереализовано:** LogManager, Restic upload, детальная страница сервиса, backup restore в UI, Alembic
4. **Баги в коде:** deployments.py использует несуществующие методы/поля
5. **Нет login endpoint:** Все API эндпоинты защищены, но получить токен невозможно через API
6. **Тестирование:** 3 уровня — интеграционные, dry-run, DinD
7. **Документация противоречит коду** в части примеров service.yml
