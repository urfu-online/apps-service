# Справочник по service.yml

Манифест `service.yml` — это основной конфигурационный файл сервиса в платформе apps-service-opus. Он описывает метаданные сервиса, маршрутизацию, проверки здоровья, настройки бэкапов и другие параметры.

## Общая структура

```yaml
name: string                    # обязательное
display_name: string            # опционально
version: string                 # опционально, по умолчанию "1.0.0"
description: string             # опционально, по умолчанию ""
type: string                    # опционально, по умолчанию "docker-compose"
visibility: string              # опционально, по умолчанию "internal"
routing: array                  # опционально, по умолчанию []
health: object                  # опционально, по умолчанию включено
backup: object                  # опционально, по умолчанию отключено
tags: array                     # опционально, по умолчанию []
```

## Обязательные поля

### `name` (строка, **обязательное**)
Уникальное имя сервиса. Должно совпадать с именем директории сервиса. Используется как идентификатор в API и UI.

**Пример:**
```yaml
name: my-web-app
```

## Основные поля

### `display_name` (строка, опционально)
Человекочитаемое название сервиса для отображения в интерфейсе. Если не указано, генерируется из `name` (заменяет дефисы на пробелы и применяет title case).

**Пример:**
```yaml
display_name: "Мой Веб-Приложение"
```

### `version` (строка, опционально)
Версия сервиса. По умолчанию `"1.0.0"`. Используется для отслеживания версий в UI и API.

**Пример:**
```yaml
version: "2.1.0"
```

### `description` (строка, опционально)
Краткое описание сервиса. По умолчанию пустая строка.

**Пример:**
```yaml
description: "Сервис для управления пользовательскими данными с REST API"
```

### `type` (строка, опционально)
Тип сервиса. В текущей реализации поддерживается только `"docker-compose"`. По умолчанию `"docker-compose"`.

**Пример:**
```yaml
type: docker-compose
```

### `visibility` (строка, опционально)
Видимость сервиса. Определяет, в какой директории находится сервис и как к нему можно обращаться.
- `"public"` — сервис доступен извне через прокси Caddy.
- `"internal"` — сервис доступен только внутри сети master-сервиса.

По умолчанию `"internal"`. Должен соответствовать фактическому расположению (`services/public/` или `services/internal/`).

**Пример:**
```yaml
visibility: public
```

### `tags` (массив строк, опционально)
Произвольные теги для категоризации и фильтрации сервисов. По умолчанию пустой массив.

**Пример:**
```yaml
tags:
  - api
  - backend
  - production
```

## Раздел `routing`

Определяет правила маршрутизации трафика к контейнерам сервиса. Каждое правило — объект со следующими полями.

### Общая структура объекта маршрутизации

```yaml
routing:
  - type: string               # обязательное: "domain", "subfolder", "port"
    domain: string             # опционально (для type: domain)
    base_domain: string        # опционально (для type: subfolder)
    path: string               # опционально (для type: subfolder)
    port: integer              # опционально (для type: port)
    strip_prefix: boolean      # опционально, по умолчанию true
    internal_port: integer     # опционально, по умолчанию 8000
    container_name: string     # опционально
    auto_subdomain: boolean    # опционально, по умолчанию false
    auto_subdomain_base: string # опционально, по умолчанию "apps.urfu.online"
```

### Поля маршрутизации

#### `type` (строка, **обязательное**)
Тип маршрута:
- `"domain"` — прямое сопоставление домена (например, `app.example.com`).
- `"subfolder"` — подпапка на базовом домене (например, `apps.example.com/my-app`).
- `"port"` — проброс порта (редко используется).

#### `domain` (строка, опционально)
Доменное имя для типа `domain`. Должно быть полным доменным именем (FQDN).

**Пример:**
```yaml
domain: myapp.example.com
```

#### `base_domain` (строка, опционально)
Базовый домен для типа `subfolder`. Используется вместе с `path`.

**Пример:**
```yaml
base_domain: apps.urfu.online
```

#### `path` (строка, опционально)
Путь (подпапка) для типа `subfolder`. Должен начинаться с `/`.

**Пример:**
```yaml
path: /my-app
```

#### `port` (целое число, опционально)
Номер порта для типа `port`. Внешний порт, на котором будет доступен сервис.

**Пример:**
```yaml
port: 8080
```

#### `strip_prefix` (логическое, опционально)
Удалять ли префикс пути при проксировании. По умолчанию `true`. Если `false`, путь передаётся в upstream как есть.

**Пример:**
```yaml
strip_prefix: false
```

#### `internal_port` (целое число, опционально)
Порт внутри контейнера, на который будет проксироваться трафик. По умолчанию `8000`.

**Пример:**
```yaml
internal_port: 3000
```

#### `container_name` (строка, опционально)
Имя конкретного контейнера для прямого проксирования. Если не указано, используется первичный контейнер сервиса.

**Пример:**
```yaml
container_name: my-app-frontend
```

#### `auto_subdomain` (логическое, опционально)
Включить ли автоматическое создание поддомена вида `{name}.{auto_subdomain_base}`. По умолчанию `false`. Если `true`, генерируется домен на основе имени сервиса и базового домена.

**Пример:**
```yaml
auto_subdomain: true
```

#### `auto_subdomain_base` (строка, опционально)
Базовый домен для автоматического поддомена. По умолчанию `"apps.urfu.online"`.

**Пример:**
```yaml
auto_subdomain_base: "apps.example.com"
```

### Примеры конфигураций маршрутизации

**Доменный маршрут:**
```yaml
routing:
  - type: domain
    domain: api.example.com
    internal_port: 8000
```

**Подпапка на базовом домене:**
```yaml
routing:
  - type: subfolder
    base_domain: apps.urfu.online
    path: /myapp
    internal_port: 3000
```

**Автоматический поддомен:**
```yaml
routing:
  - type: domain
    auto_subdomain: true
    auto_subdomain_base: "apps.urfu.online"
    internal_port: 8080
```

## Раздел `health`

Настройки проверки здоровья сервиса.

### Структура

```yaml
health:
  enabled: boolean            # опционально, по умолчанию true
  endpoint: string            # опционально, по умолчанию "/health"
  interval: string            # опционально, по умолчанию "30s"
  timeout: string             # опционально, по умолчанию "10s"
  retries: integer            # опционально, по умолчанию 3
```

### Поля

#### `enabled` (логическое, опционально)
Включить ли проверку здоровья. По умолчанию `true`.

#### `endpoint` (строка, опционально)
HTTP-эндпоинт для проверки здоровья. Должен возвращать `200 OK`. По умолчанию `"/health"`.

#### `interval` (строка, опционально)
Интервал между проверками в формате Go duration (например, `"30s"`, `"1m"`). По умолчанию `"30s"`.

#### `timeout` (строка, опционально)
Таймаут HTTP-запроса в формате Go duration. По умолчанию `"10s"`.

#### `retries` (целое число, опционально)
Количество повторных попыток перед пометкой сервиса как нездорового. По умолчанию `3`.

### Пример

```yaml
health:
  enabled: true
  endpoint: /healthz
  interval: 15s
  timeout: 5s
  retries: 2
```

## Раздел `backup`

Настройки автоматического резервного копирования.

### Структура

```yaml
backup:
  enabled: boolean            # опционально, по умолчанию false
  schedule: string            # опционально, по умолчанию "0 2 * * *" (каждый день в 2:00)
  retention: integer          # опционально, по умолчанию 7 (дней)
  paths: array                # опционально, по умолчанию []
  databases: array            # опционально, по умолчанию []
```

### Поля

#### `enabled` (логическое, опционально)
Включить ли автоматическое резервное копирование. По умолчанию `false`.

#### `schedule` (строка, опционально)
Расписание в формате cron. По умолчанию `"0 2 * * *"` (каждый день в 2:00).

#### `retention` (целое число, опционально)
Срок хранения бэкапов в днях. По умолчанию `7`.

#### `paths` (массив строк, опционально)
Список путей внутри контейнера для резервного копирования (используется rsync). По умолчанию пустой массив.

**Пример:**
```yaml
paths:
  - /var/lib/data
  - /etc/config
```

#### `databases` (массив объектов, опционально)
Список баз данных для резервного копирования (используется pg_dump для PostgreSQL). Каждый объект должен содержать поля `type`, `host`, `port`, `name`, `user`, `password` (или ссылку на переменные окружения). По умолчанию пустой массив.

**Пример:**
```yaml
databases:
  - type: postgresql
    host: db
    port: 5432
    name: mydb
    user: ${DB_USER}
    password: ${DB_PASSWORD}
```

### Пример

```yaml
backup:
  enabled: true
  schedule: "0 3 * * *"
  retention: 30
  paths:
    - /app/uploads
  databases:
    - type: postgresql
      host: postgres
      port: 5432
      name: app_db
```

## Runtime-поля (генерируются автоматически)

Следующие поля добавляются автоматически при загрузке манифеста и не должны указываться в `service.yml`:

- `path` — абсолютный путь к директории сервиса.
- `status` — текущий статус (`"unknown"`, `"healthy"`, `"unhealthy"`, `"deploying"` и т.д.).
- `last_deployed` — дата и время последнего деплоя.
- `container_ids` — список идентификаторов Docker-контейнеров.

## Локальные переопределения (service.local.yml)

Для разработки можно создать файл `service.local.yml` в той же директории, что и `service.yml`. Его содержимое будет объединено с основным манифестом (приоритет у локального файла). Этот файл **не коммитится** в репозиторий.

**Пример `service.local.yml`:**
```yaml
routing:
  - type: subfolder
    base_domain: localhost
    path: /myapp
    internal_port: 3000
health:
  endpoint: /health
```

## Полный пример

```yaml
name: api-gateway
display_name: API Gateway
version: "1.2.0"
description: "Единая точка входа для всех микросервисов"
type: docker-compose
visibility: public
routing:
  - type: domain
    domain: api.company.com
    internal_port: 8080
    strip_prefix: true
  - type: subfolder
    base_domain: apps.company.com
    path: /gateway
    internal_port: 8080
health:
  enabled: true
  endpoint: /health
  interval: 30s
  timeout: 5s
  retries: 3
backup:
  enabled: false
tags:
  - api
  - gateway
  - production
```

## Примечания

<!-- КОММЕНТАРИЙ: В discovery.py есть поле `container_name` в RoutingConfigModel, но неясно, используется ли оно для прямого проксирования к конкретному контейнеру или для именования контейнера в docker-compose. В примерах тестовых фикстур используется `container_name: test-web-app`. Рекомендуется уточнить у разработчиков. -->

<!-- КОММЕНТАРИЙ: Поле `auto_subdomain` генерирует домен вида `{name}.{auto_subdomain_base}`, но неясно, требуется ли также указывать `type: domain` или это отдельный тип маршрутизации. В коде проверяется `route.auto_subdomain` и строится домен. Лучше добавить пример. -->

<!-- КОММЕНТАРИЙ: Поле `databases` в backup предполагает поддержку только PostgreSQL? В коде BackupConfigModel имеет тип `list[dict]` без валидации. Нужно уточнить поддерживаемые типы БД. -->

## Ссылки

- [Исходный код discovery.py](https://github.com/urfu-online/apps-service/blob/master/_core/master/app/services/discovery.py)
- [Примеры service.yml в тестовых фикстурах](../_core/master/test-fixtures/services/)
- [Документация по маршрутизации Caddy](../development/caddy-configuration.md)