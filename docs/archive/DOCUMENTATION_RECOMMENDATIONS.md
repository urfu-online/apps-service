# Рекомендации по улучшению документации

> **Дата:** 2026-04-16
> **На основе:** DOCUMENTATION_ANALYSIS.md

---

## Быстрые победы (можно сделать за 1-2 часа)

### 1. Исправить критические ошибки в примерах

**Файлы для редактирования:**
- `docs/examples.md`
- `docs/getting-started/first-service.md`
- `docs/user-guide/services.md`

**Конкретные изменения:**
```yaml
# ДО (сейчас):
routing:
  - type: domain
    domain: myapp.example.com
    internal_port: 80

# ПОСЛЕ (должно быть):
routing:
  - type: domain
    domain: myapp.example.com
    internal_port: 80
    container_name: my-app  # ⚠️ ОБЯЗАТЕЛЬНО
```

**Также добавить предупреждение:**
```markdown
> ⚠️ **Важно:** Поле `container_name` обязательно. Без него Caddy будет 
> проксировать на хост-машину вместо контейнера, что создаёт конфликты 
> портов и проблемы с безопасностью.
```

### 2. Добавить баннеры "Не реализовано"

Добавить в начало файлов:

**`docs/user-guide/monitoring.md`:**
```markdown
> ⚠️ **Статус реализации:**
> - ✅ Health checks — работают
> - ✅ Docker API логи — работают
> - ❌ Loki — не реализован
> - ❌ Prometheus/Grafana — не реализовано
```

**`docs/user-guide/backup.md`:**
```markdown
> ⚠️ **Статус реализации:**
> - ✅ Файловые бэкапы (rsync) — работают
> - ✅ Бэкапы БД (pg_dump) — работают
> - ❌ Restic upload — скрипты отсутствуют
> - ❌ Restore в UI — заглушка
```

**`docs/examples.md`:**
```markdown
> ⚠️ **Поддерживаемые типы сервисов:**
> - ✅ `docker-compose` — полностью реализован
> - ❌ `static`, `docker`, `external` — не реализованы
```

### 3. Исправить имя CLI

Заменить `ops` на `platform` в:
- `docs/development/deployment-runbook.md`
- `docs/development/upgrade-report-2026-04-15.md`
- `docs/plan/deployment-runbook.md`

### 4. Создать файл TROUBLESHOOTING.md

Создать `docs/TROUBLESHOOTING.md` с типичными проблемами:

```markdown
# Устранение неполадок

## Сервис недоступен по домену

**Симптом:** 502 Bad Gateway

**Причины:**
1. Не указан `container_name` в `service.yml`
2. Контейнер не запущен
3. Неправильный `internal_port`

**Решение:**
```bash
# Проверить что контейнер запущен
docker ps | grep <service>

# Проверить логи
docker logs <container>

# Проверить Caddy конфиг
cat _core/caddy/conf.d/<service>.caddy
```

## Не работает health check

**Симптом:** Сервис показывается как unhealthy

**Причины:**
1. Неправильный `health.endpoint`
2. Endpoint не возвращает 200
3. Сервис не присоединён к `platform_network`
```

---

## Средние задачи (1-2 дня)

### 5. Создать полный reference service.yml

**Создать файл:** `docs/reference/service-yml.md`

```markdown
# Полный reference service.yml

## Обязательные поля

| Поле | Тип | Описание | Пример |
|------|-----|----------|--------|
| `name` | string | Уникальное имя сервиса | `my-app` |
| `version` | string | Версия (SemVer) | `1.0.0` |
| `type` | enum | Тип сервиса | `docker-compose` |
| `visibility` | enum | Видимость | `public` |

## Роутинг

### type: domain

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| `domain` | string | ✅ | Домен сервиса |
| `internal_port` | int | ✅ | Порт внутри контейнера |
| `container_name` | string | ✅ | Имя Docker контейнера |

### type: subfolder

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| `base_domain` | string | ✅ | Базовый домен |
| `path` | string | ✅ | Путь (с ведущим /) |
| `strip_prefix` | bool | ❌ | Убирать prefix | 
| `internal_port` | int | ✅ | Порт внутри контейнера |
| `container_name` | string | ✅ | Имя Docker контейнера |

## Полный пример

```yaml
name: my-service
display_name: "Мой Сервис"
version: "1.0.0"
description: "Описание сервиса"
type: docker-compose
visibility: public

routing:
  - type: domain
    domain: myservice.example.com
    internal_port: 8000
    container_name: my-service

health:
  enabled: true
  endpoint: /health
  interval: 30s
  timeout: 10s
  retries: 3

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
```

### 6. Написать гайд по локальной разработке

**Создать файл:** `docs/development/local-setup.md`

```markdown
# Локальная разработка

## Требования

- Python 3.12
- Poetry
- Docker + Docker Compose plugin
- Make

## Первый запуск

```bash
# 1. Клонировать репозиторий
git clone <repo>
cd apps-service-opus

# 2. Установить зависимости
cd _core/master
poetry install

# 3. Запустить dev окружение
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 4. Проверить
curl http://localhost:8000/healthz
```

## Запуск тестов

```bash
make test
```

## Структура для разработки

...
```

### 7. Написать гайд по аутентификации

**Создать файл:** `docs/development/authentication.md`

```markdown
# Аутентификация в платформе

## Два режима

### Builtin auth (по умолчанию для local)

- Хранение: SQLite (`master.db`)
- Хеширование: bcrypt
- Токен: просто `str(user_id)` (⚠️ временное решение)

### Keycloak (для production)

- Внешний сервер Keycloak
- OAuth2/OIDC
- Realm: нужно создать
- Client: нужно настроить

## Как получить токен

> ⚠️ **Важно:** Login endpoint в API отсутствует. Токен нужно получать:
> - Для builtin: напрямую из БД (временное решение)
> - Для Keycloak: через Keycloak API напрямую

### Получение токена от Keycloak

```bash
curl -X POST https://keycloak.example.com/realms/{realm}/protocol/openid-connect/token \
  -d "grant_type=password" \
  -d "client_id={client_id}" \
  -d "username={username}" \
  -d "password={password}"
```
```

### 8. Создать глоссарий терминов

**Создать файл:** `docs/GLOSSARY.md`

```markdown
# Глоссарий

| Термин | Описание |
|--------|----------|
| **Master Service** | Центральный сервис управления (FastAPI + NiceGUI) |
| **service.yml** | Манифест сервиса с конфигурацией |
| **platform CLI** | Утилита командной строки (`platform`) |
| **public/internal** | Видимость сервиса (извне/только в сети) |
| **routing** | Настройка маршрутизации (domain/subfolder/port) |
| **health check** | Проверка работоспособности сервиса |
| **local override** | Локальное переопределение через `service.local.yml` |
```

---

## Крупные задачи (1-2 недели)

### 9. Переписать docs/examples.md

Текущий файл смешивает разные типы сервисов, включая неподдерживаемые.

**Структура:**
```markdown
# Примеры сервисов

## Базовый веб-сервер (nginx)

```yaml
# service.yml
name: static-site
version: "1.0.0"
type: docker-compose
visibility: public

routing:
  - type: domain
    domain: site.example.com
    internal_port: 80
    container_name: static-site

health:
  enabled: true
  endpoint: /
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  static-site:
    image: nginx:alpine
    container_name: static-site
    networks:
      - platform_network

networks:
  platform_network:
    external: true
```

## FastAPI + PostgreSQL

...

## Node.js сервис

...
```

### 10. Создать интерактивные схемы

Добавить в `docs/architecture.md`:
- Sequence diagram для деплоя сервиса
- Sequence diagram для health check
- ER-диаграмму базы данных

Инструменты: Mermaid (уже используется в некоторых местах)

### 11. Реорганизовать docs/development/

**Текущая структура:**
```
docs/development/
  index.md
  master-service.md
  testing.md
  workflow.md
  release-process.md
  deployment-runbook.md
  upgrade-to-release.md
  upgrade-report-2026-04-15.md
  guides-wishlist.md
```

**Предлагаемая структура:**
```
docs/development/
  index.md                    # навигация
  setup/
    local-setup.md            # локальная разработка
    docker-setup.md           # работа с Docker
  guides/
    master-service.md         # архитектура Master Service
    adding-api-endpoint.md    # как добавить endpoint
    nicegui.md                # работа с UI
    authentication.md         # аутентификация
    caddy-templates.md        # шаблоны Caddy
  process/
    workflow.md               # работа с задачами
    testing.md                # тестирование
    release-process.md        # выпуск релиза
    deployment-runbook.md     # обновление платформы
  reference/
    er-diagram.md             # схема БД
    api-reference.md          # полный reference API
```

---

## Процесс поддержания актуальности

### 12. Внедрить проверки документации

**В Makefile добавить:**
```makefile
# Проверка документации
docs-check:
	@echo "Проверка битых ссылок..."
	@# TODO: добавить проверку
	@echo "Проверка примеров кода..."
	@# TODO: валидировать YAML примеры

docs-serve:
	@cd docs && mkdocs serve

docs-build:
	@cd docs && mkdocs build --strict
```

### 13. Создать шаблон для документации новых фич

**Шаблон:** `docs/.template.md`

```markdown
# Название фичи

> Статус: implemented / in-progress / planned
> Добавлено в версии: X.Y.Z

## Описание

Краткое описание что делает эта фича.

## Использование

### Пример кода

```yaml
# Пример с пояснениями
```

## Конфигурация

| Параметр | Тип | Описание | По умолчанию |
|----------|-----|----------|--------------|
| ... | ... | ... | ... |

## Ограничения

- Ограничение 1
- Ограничение 2

## Устранение неполадок

### Проблема: ...

**Решение:** ...
```

### 14. Внедрить принцип "Documentation Driven Development"

Для новых фич:
1. Сначала написать документацию (что должно работать)
2. Затем реализовать код
3. В README.md добавить ссылку

Это поможет избежать рассинхронизации.

---

## Приоритетная очередь

### Неделя 1
1. Исправить примеры (`container_name`) ⏱️ 1ч
2. Добавить баннеры "Не реализовано" ⏱️ 30мин
3. Исправить `ops` → `platform` ⏱️ 30мин
4. Создать TROUBLESHOOTING.md ⏱️ 2ч

### Неделя 2
5. Создать reference/service-yml.md ⏱️ 3ч
6. Написать local-setup.md ⏱️ 2ч
7. Написать authentication.md ⏱️ 2ч

### Неделя 3-4
8. Реорганизовать docs/development/ ⏱️ 1 день
9. Переписать docs/examples.md ⏱️ 1 день
10. Добавить схемы в architecture.md ⏱️ 1 день

---

## Метрики успеха

Через месяц после внедрения рекомендаций:

| Метрика | Текущая | Целевая |
|---------|---------|---------|
| Оценка полноты | 3/5 | 4/5 |
| Оценка актуальности | 2/5 | 4/5 |
| Оценка точности | 2/5 | 4/5 |
| Количество "быстрых побед" | - | 4/4 |
| Время onboarding нового разработчика | ? | < 2 часов |
