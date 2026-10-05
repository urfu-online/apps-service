# Инструкция для ИИ: Создание service.yml для нового сервиса

> **Назначение:** Этот документ — инструкция для ИИ-ассистента. Следуя ей, ИИ должен:
> 1. Задать пользователю уточняющие вопросы (Шаг 1).
> 2. Сгенерировать `service.yml` на основе ответов (Шаг 2).
> 3. Выдать чек-лист требований к подключаемому сервису (Шаг 3).
>
> **Источник истины:** код, а не документация. Поля и поведение описаны на основе
> `_core/master/app/services/discovery.py`, `_core/master/app/services/backup_models.py`,
> `_core/master/app/services/caddy_manager.py`, `_core/master/app/services/health_checker.py`,
> `_core/caddy/templates/*.j2`, `_core/platform-cli/apps_platform/commands/services_create.py`.


**IMPORTANT:**
- `service.yml` должен находиться в корне проекта, рядом с `docker-compose.yml`, `.env`, `.env.example`.
---

## 0. Что реализовано, а что нет

Прежде чем генерировать манифест, ИИ должен понимать, какие поля реально обрабатываются системой, а какие — игнорируются.

### Поля, которые обрабатываются системой

| Поле | Модель | Статус | Примечание |
|---|---|---|---|
| `name` | `ServiceManifest` | ✅ Обязательно | Уникальный slug, имя директории |
| `display_name` | `ServiceManifest` | ✅ | Человекочитаемое имя для UI |
| `version` | `ServiceManifest` | ✅ | По умолчанию `"1.0.0"` |
| `description` | `ServiceManifest` | ✅ | По умолчанию `""` |
| `type` | `ServiceManifest` | ✅ | По умолчанию `"docker-compose"`. Только `docker-compose` реализован |
| `visibility` | `ServiceManifest` | ✅ | `"public"` или `"internal"`, по умолчанию `"internal"`. Определяется расположением директории |
| `routing` | `list[RoutingConfigModel]` | ✅ | По умолчанию `[]` |
| `routing[].type` | `RoutingConfigModel` | ✅ | `"domain"`, `"subfolder"`, `"port"`, `"auto_subdomain"` |
| `routing[].domain` | `RoutingConfigModel` | ✅ | Для `type: domain` |
| `routing[].base_domain` | `RoutingConfigModel` | ✅ | Для `subfolder`, `auto_subdomain`. По умолчанию `"apps.urfu.online"` для `auto_subdomain` |
| `routing[].path` | `RoutingConfigModel` | ✅ | Для `subfolder`. Должен начинаться с `/` |
| `routing[].port` | `RoutingConfigModel` | ✅ | Для `port`. Внешний порт |
| `routing[].internal_port` | `RoutingConfigModel` | ✅ | Порт контейнера. По умолчанию `8000` |
| `routing[].container_name` | `RoutingConfigModel` | ✅ **Критично** | Имя Docker-контейнера для проксирования. Без него Caddy проксирует на `host.docker.internal` |
| `routing[].strip_prefix` | `RoutingConfigModel` | ✅ | По умолчанию `true`. Добавляет заголовок `X-Forwarded-Prefix` |
| `health` | `HealthConfigModel` | ✅ | По умолчанию включён |
| `health.enabled` | `HealthConfigModel` | ✅ | По умолчанию `true` |
| `health.endpoint` | `HealthConfigModel` | ✅ | По умолчанию `"/health"` |
| `health.interval` | `HealthConfigModel` | ✅ | По умолчанию `"30s"` (формат Go duration) |
| `health.timeout` | `HealthConfigModel` | ✅ | По умолчанию `"10s"` |
| `health.retries` | `HealthConfigModel` | ✅ | По умолчанию `3` |
| `backup` | `BackupConfig` | ✅ | По умолчанию отключён. Модель `extra="forbid"` — лишние поля вызывают ошибку |
| `backup.enabled` | `BackupConfig` | ✅ | По умолчанию `false`. Если `true`, требует env `KOPIA_REPOSITORY` и `KOPIA_REPOSITORY_PASSWORD` |
| `backup.schedule` | `BackupConfig` | ✅ | Cron-выражение, по умолчанию `"0 2 * * *"`. Валидируется через `croniter` |
| `backup.retention_days` | `BackupConfig` | ✅ | По умолчанию `7`, диапазон `1..3650`. **Важно:** поле называется `retention_days`, не `retention` |
| `backup.paths` | `BackupConfig` | ✅ | `List[str]`, по умолчанию `[]` |
| `backup.databases` | `BackupConfig` | ✅ | `List[str]` — **строки подключения** (например `"postgresql://user:pass@host:5432/db"`), не объекты |
| `backup.kopia_policy` | `BackupConfig` | ✅ | Dict с ключами `keep-daily`, `keep-weekly`, `keep-monthly`, `keep-annual` |
| `backup.storage_type` | `BackupConfig` | ✅ | `"filesystem"` (по умолчанию) или `"s3"` |
| `backup.s3_endpoint` | `BackupConfig` | ✅ | Обязателен при `storage_type: "s3"` |
| `backup.s3_bucket` | `BackupConfig` | ✅ | Обязателен при `storage_type: "s3"` |
| `tags` | `ServiceManifest` | ✅ | `list[str]`, по умолчанию `[]` |

### Поля, которые ИГНОРИРУЮТСЯ системой

Эти поля встречаются в документации (`docs/user-guide/services.md`, `shared/templates/service.yml`) и могут быть указаны в YAML, но **не обрабатываются** `ServiceManifest` (Pydantic v1 `extra="ignore"` по умолчанию). ИИ **не должен** включать их в генерируемый `service.yml`, чтобы не вводить пользователя в заблуждение.

| Поле | Статус | Примечание |
|---|---|---|
| `maintainer` | ❌ Игнорируется | Не в модели `ServiceManifest` |
| `repository` | ❌ Игнорируется | Не в модели `ServiceManifest` |
| `resources` | ❌ Игнорируется | `memory_limit`, `cpu_limit` не применяются |
| `logging` | ❌ Игнорируется | Loki-интеграция не реализована |
| `dependencies` | ❌ Игнорируется | Зависимости не обрабатываются |
| `environment` | ❌ Игнорируется | Используйте `.env` файл и `docker-compose.yml` |
| `secrets` | ❌ Игнорируется | Секреты не реализованы, используйте `.env` |
| `hooks` | ❌ Игнорируется | Хуки не выполняются |
| `notifications` | ❌ Игнорируется | Telegram-уведомления о health check работают автономно через `TelegramNotifier`, настройка в `service.yml` не нужна |
| `headers` | ❌ Игнорируется | Заголовки задаются в Caddy-шаблонах, не в манифесте |

### Миграция старых полей backup

`discovery.py` содержит валидатор `migrate_backup_config`, который автоматически преобразует:
- `backup.retention` → `backup.retention_days` (старое поле → новое)
- `backup.databases: [{type, container, database, ...}]` → `backup.databases: ["postgresql://..."]` (объекты → строки подключения)

ИИ должен генерировать **новый формат** (`retention_days`, `databases: [str]`), но знать, что старые форматы будут автоматически мигрированы.

---

## 1. Шаг 1: Уточняющие вопросы

ИИ должен задать пользователю следующие вопросы. Если ответ очевиден из контекста (например, пользователь уже назвал сервис), пропустить соответствующий вопрос. Использовать минимум вопросов — объединять связанные в один блок.

### 1.1. Идентификация сервиса

**Вопросы:**
1. **Имя сервиса** — уникальный идентификатор в kebab-case (например `my-api-service`). Должно соответствовать regex `^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$`. Используется как имя директории и в API.
2. **Человекочитаемое название** (опционально) — для отображения в UI. Если не указано, генерируется из имени (дефисы → пробелы, title case).
3. **Описание** (опционально) — краткое описание назначения сервиса.
4. **Версия** (опционально) — по умолчанию `"1.0.0"`.

### 1.2. Видимость

**Вопрос:**
- Сервис должен быть доступен извне (через интернет) или только внутри Docker-сети платформы?

**Варианты:**
- `public` — сервис доступен извне через Caddy reverse proxy. Размещается в `services/public/`.
- `internal` — сервис доступен только из приватных IP-диапазонов (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16). Размещается в `services/internal/`. Caddy отклоняет внешние запросы с `403 Access Denied`.

По умолчанию: `internal`.

### 1.3. Маршрутизация

**Вопросы:**
1. **Тип маршрутизации** — выбрать один или несколько:
   - `auto_subdomain` — автоматический поддомен вида `{имя-сервиса}.{base_domain}`. SSL-сертификат выпускается автоматически через on-demand TLS. **Рекомендуется по умолчанию.**
   - `domain` — собственный домен (FQDN). SSL автоматически через Let's Encrypt.
   - `subfolder` — подпапка на базовом домене (например `apps.example.com/my-service`).
   - `port` — проброс порта (редко используется, без TLS).
2. **Базовый домен** — для `auto_subdomain` и `subfolder`. По умолчанию `apps.urfu.online` для `auto_subdomain`.
3. **Свой домен** — для `type: domain`. Полное доменное имя (FQDN).
4. **Путь** — для `subfolder`. Должен начинаться с `/` (например `/my-service`).
5. **Внешний порт** — для `port`. Порт на хосте, который Caddy будет слушать.
6. **Внутренний порт контейнера** — порт, на котором сервис слушает внутри контейнера. По умолчанию `8000`.
7. **Имя Docker-контейнера** — имя контейнера из `docker-compose.yml`, к которому Caddy будет проксировать. **Обязательно для корректной работы.** Должно совпадать с `container_name` в `docker-compose.yml`.
8. **Несколько маршрутов** — если сервис должен быть доступен по нескольким URL, указать все маршруты.

### 1.4. Health check

**Вопросы:**
1. **Есть ли в сервисе health endpoint?** — HTTP-эндпоинт, возвращающий `200 OK`.
   - Если да: указать путь (по умолчанию `/health`).
   - Если нет: отключить health check (`enabled: false`) — сервис всегда будет считаться healthy.
2. **Интервал проверки** (опционально) — по умолчанию `30s`.
3. **Таймаут** (опционально) — по умолчанию `10s`.

> **Важно:** Health checker (`_get_health_url`) обрабатывает только маршруты типа `domain`, `subfolder`, `port`. Для `auto_subdomain` URL для проверки не строится (метод возвращает `None`). Если у сервиса только `auto_subdomain` маршрутизация, health check не будет работать — рекомендуется либо добавить дополнительный маршрут типа `domain`/`subfolder`/`port`, либо отключить health check.

### 1.5. Резервное копирование

**Вопросы:**
1. **Нужны ли бэкапы?** — по умолчанию отключено.
2. **Что бэкапить?** — пути внутри контейнера (список строк) и/или базы данных (строки подключения).
3. **Расписание** — cron-выражение, по умолчанию `"0 2 * * *"` (каждый день в 2:00).
4. **Срок хранения** — в днях, по умолчанию `7`.
5. **Тип хранилища** — `filesystem` (по умолчанию) или `s3` (требует `s3_endpoint` и `s3_bucket`).

> **Важно:** Если `backup.enabled: true`, в окружении master-сервиса должны быть установлены переменные `KOPIA_REPOSITORY` и `KOPIA_REPOSITORY_PASSWORD`. ИИ должен предупредить об этом.

### 1.6. Теги

**Вопрос (опционально):**
- Произвольные теги для категоризации (например `api`, `backend`, `production`).

---

## 2. Шаг 2: Генерация service.yml

После получения ответов ИИ генерирует `service.yml` по следующим правилам.

### 2.1. Правила генерации

1. **Включать только обрабатываемые поля.** Не добавлять `maintainer`, `resources`, `logging`, `dependencies`, `secrets`, `hooks`, `notifications`, `environment`, `headers` — они игнорируются системой.
2. **`container_name` обязателен** в каждом объекте `routing`. Без него Caddy проксирует на `host.docker.internal:{port}` — это legacy-режим с проблемами безопасности и конфликтами портов.
3. **`internal_port`** должен соответствовать порту, на котором сервис реально слушает внутри контейнера.
4. **`type`** всегда `docker-compose` (единственный реализованный тип).
5. **`backup.databases`** — список строк подключения (например `"postgresql://user:pass@host:5432/db"`), не объектов с полями `type`/`container`/`database`.
6. **`backup.retention_days`** — поле называется `retention_days`, не `retention`.
7. **`backup`** — модель `extra="forbid"`: нельзя добавлять поля, не предусмотренные моделью (например `storage_type: sftp` вызовет ошибку — допустимы только `filesystem` и `s3`).
8. **`visibility`** — указывается в манифесте, но фактически определяется расположением директории (`services/public/` или `services/internal/`).
9. **Имя сервиса** — kebab-case, соответствует имени директории.
10. **Несколько маршрутов** — можно указать несколько объектов в `routing` (например, `auto_subdomain` + `domain`).

### 2.2. Шаблон

```yaml
name: <имя-сервиса>                    # kebab-case, обязательно
display_name: "<Название>"             # опционально
version: "<версия>"                    # опционально, по умолчанию "1.0.0"
description: "<описание>"              # опционально
type: docker-compose                   # обязательно, только docker-compose
visibility: <public|internal>          # обязательно (определяется директорией)

routing:                               # опционально, по умолчанию []
  - type: <domain|subfolder|port|auto_subdomain>
    # Поля зависят от типа — см. примеры ниже
    internal_port: <порт>              # порт контейнера, по умолчанию 8000
    container_name: <имя-контейнера>    # ОБЯЗАТЕЛЬНО — имя Docker-контейнера
    strip_prefix: <true|false>         # опционально, по умолчанию true

health:                                # опционально, по умолчанию включён
  enabled: <true|false>                # опционально, по умолчанию true
  endpoint: </путь>                    # опционально, по умолчанию /health
  interval: "<длительность>"           # опционально, по умолчанию "30s"
  timeout: "<длительность>"            # опционально, по умолчанию "10s"
  retries: <число>                     # опционально, по умолчанию 3

backup:                                # опционально, по умолчанию отключён
  enabled: <true|false>                # опционально, по умолчанию false
  schedule: "<cron>"                   # опционально, по умолчанию "0 2 * * *"
  retention_days: <число>              # опционально, по умолчанию 7
  paths:                              # опционально, по умолчанию []
    - "<путь-в-контейнере>"
  databases:                          # опционально, по умолчанию []
    - "<строка-подключения>"
  storage_type: <filesystem|s3>        # опционально, по умолчанию filesystem
  # s3_endpoint и s3_bucket — обязательны при storage_type: s3

tags:                                  # опционально, по умолчанию []
  - "<тег>"
```

### 2.3. Примеры маршрутизации

#### auto_subdomain (по умолчанию)

```yaml
routing:
  - type: auto_subdomain
    base_domain: apps.urfu.online       # опционально, по умолчанию apps.urfu.online
    internal_port: 8000
    container_name: my-service
```

Сервис доступен по адресу `https://my-service.apps.urfu.online`. SSL выпускается через on-demand TLS при первом запросе. Платформа валидирует домен через `/api/tls/validate`.

#### domain

```yaml
routing:
  - type: domain
    domain: my-service.example.com
    internal_port: 8000
    container_name: my-service
```

Сервис доступен по адресу `https://my-service.example.com`. SSL выпускается автоматически через Let's Encrypt. Требуется DNS A-запись на IP сервера.

#### subfolder

```yaml
routing:
  - type: subfolder
    base_domain: apps.example.com
    path: /my-service
    strip_prefix: true                  # добавляет X-Forwarded-Prefix
    internal_port: 8000
    container_name: my-service
```

Сервис доступен по адресу `https://apps.example.com/my-service`. Несколько сервисов с одним `base_domain` группируются в один Caddy site-блок.

#### port

```yaml
routing:
  - type: port
    port: 8081                          # внешний порт
    internal_port: 8000                 # порт контейнера
    container_name: my-service
```

Caddy слушает на порту `8081` и проксирует в контейнер. Без TLS.

#### Несколько маршрутов

```yaml
routing:
  - type: auto_subdomain
    base_domain: apps.urfu.online
    internal_port: 8000
    container_name: my-service
  - type: domain
    domain: api.example.com
    internal_port: 8000
    container_name: my-service
```

### 2.4. Пример с бэкапом

```yaml
backup:
  enabled: true
  schedule: "0 2 * * *"                  # каждый день в 2:00
  retention_days: 30
  paths:
    - /app/data
    - /app/uploads
  databases:
    - "postgresql://user:pass@db:5432/mydb"
  storage_type: filesystem
```

> Для `storage_type: s3`:
> ```yaml
> backup:
>   enabled: true
>   storage_type: s3
>   s3_endpoint: "https://s3.example.com"
>   s3_bucket: "my-backups"
> ```

### 2.5. Полный пример

```yaml
name: user-api
display_name: "API пользователей"
version: "2.1.0"
description: "Микросервис управления пользователями"
type: docker-compose
visibility: public

routing:
  - type: auto_subdomain
    base_domain: apps.urfu.online
    internal_port: 8000
    container_name: user-api

health:
  enabled: true
  endpoint: /health
  interval: 30s
  timeout: 10s
  retries: 3

backup:
  enabled: true
  schedule: "0 2 * * *"
  retention_days: 30
  paths:
    - /app/data
  databases:
    - "postgresql://user:pass@db:5432/users"
  storage_type: filesystem

tags:
  - api
  - backend
  - production
```

---

## 3. Шаг 3: Требования к подключаемому сервису

После генерации `service.yml` ИИ должен выдать пользователю чек-лист требований, которым должен удовлетворять сервис и его `docker-compose.yml`. Этот чек-лист основан на том, как система реально работает.

### 3.1. Структура директорий

Сервис должен быть размещён по пути:

```
services/
├── public/                    # для visibility: public
│   └── <имя-сервиса>/
│       ├── service.yml        # сгенерированный манифест
│       ├── docker-compose.yml # конфигурация Docker Compose
│       ├── .env               # переменные окружения (не коммитится)
│       └── ...                 # код приложения, Dockerfile и т.д.
└── internal/                  # для visibility: internal
    └── <имя-сервиса>/
        └── ...
```

> Имя директории **должно совпадать** с полем `name` в `service.yml`.

### 3.2. docker-compose.yml — обязательные требования

#### Docker-сеть

Сервис должен присоединиться к внешней сети `platform_network`. Это сеть, через которую Caddy обращается к контейнерам по имени.

```yaml
services:
  <имя-сервиса>:
    # ...
    networks:
      - platform

networks:
  platform:
    external: true
    name: platform_network
```

> Без подключения к `platform_network` Caddy не сможет разрешить имя `container_name` и проксирование не сработает.

#### Имя контейнера

Поле `container_name` в `docker-compose.yml` **должно совпадать** со значением `container_name` в `routing` манифеста `service.yml`:

```yaml
services:
  my-service:                           # имя сервиса в compose
    container_name: my-service           # ← должно совпадать с routing[].container_name
    # ...
```

Caddy генерирует директиву `reverse_proxy http://{container_name}:{internal_port}`. Если имя контейнера не совпадает, DNS-резолвинг внутри Docker-сети завершится ошибкой.

#### Порт контейнера

Контейнер должен слушать на порту, указанном в `internal_port` (по умолчанию `8000`). Это порт **внутри** контейнера, не внешний проброс.

```yaml
services:
  my-service:
    container_name: my-service
    # internal_port: 8000 в service.yml означает:
    # приложение внутри контейнера должно слушать на 8000
    # проброс порта наружу НЕ требуется (Caddy проксирует через Docker-сеть)
```

> **Не нужно** пробрасывать порт наружу через `ports:` — Caddy обращается к контейнеру через Docker-сеть `platform_network` по имени контейнера. Проброс порта нужен только если вы хотите локальный доступ без Caddy.

#### Метка для Docker-менеджера (рекомендуется)

DockerManager ищет контейнеры по лейблу `platform.service={name}` для операций `stop`, `restart`, `logs`, `stats`. Добавьте лейбл в `docker-compose.yml`:

```yaml
services:
  my-service:
    container_name: my-service
    labels:
      - "platform.service=my-service"
```

> Без этого лейбла команды `platform logs`, `platform status` могут не найти контейнер. Команда `platform deploy` использует `docker compose up` напрямую и лейбл не требуется, но для логов и статуса он необходим.

#### Прокси внутри фронтенда: коллизии DNS-имён на platform_network

Если внутри фронтенд-контейнера есть обратный прокси (nginx и т.п.), который ходит на бэкенд по имени compose-сервиса (например `proxy_pass http://backend:8000`), учтите: фронтенд подключён к общей сети `platform_network`, где другие сервисы могут иметь контейнеры с теми же алиасами (`backend`, `frontend`, `db`, `api`). Docker DNS разрешает имя по **всем** сетям контейнера, и при совпадении алиасов результат недетерминирован. nginx дополнительно кеширует разрешение при старте — в итоге `/api/*` стабильно падает с `502` и `connect() failed (111: Connection refused)` на IP из чужой подсети, а до своего бэкенда трафик не доходит (бэкенд в логах молчит).

Правила:

1. В `proxy_pass` используйте **уникальное** имя — `container_name` (например `urfu_forms_backend`), а не имя compose-сервиса (`backend`).
2. Для устойчивости к перезапускам бэкенда (смена IP) настройте рантайм-резолвер:

   ```nginx
   location /api/ {
       resolver 127.0.0.11 valid=10s ipv6=off;   # встроенный DNS Docker
       set $backend_upstream http://urfu_forms_backend:8000;
       proxy_pass $backend_upstream;
   }
   ```

   С переменной в `proxy_pass` nginx передаёт URI как есть (без замены префикса) — для `location /api/` это обычно и требуется.
3. Аналогично для имён БД и других контейнеров: уникальные `container_name` или алиасы с префиксом проекта.

Диагностика коллизии:

```bash
docker network inspect platform_network --format '{{range .Containers}}{{.IPv4Address}}  {{.Name}}{{"\n"}}{{end}}' | sort
docker exec <frontend-container> getent hosts backend <container_name_бэкенда>
```

### 3.3. Health endpoint — требования к приложению

Если `health.enabled: true` (по умолчанию):

1. **Приложение должно отвечать `200 OK`** на HTTP GET-запрос по пути `health.endpoint` (по умолчанию `/health`).
2. **Любой другой статус** помечает сервис как unhealthy.
3. **Health checker** делает запрос с таймаутом `health.timeout` (по умолчанию `10s`) каждые `30 секунд` (инфейсный цикл в `main.py`, не настраивается через манифест).
4. **URL для проверки** строится из **первого подходящего маршрута**:
   - `domain` → `https://{domain}{health.endpoint}`
   - `subfolder` → `https://{base_domain}{path}{health.endpoint}`
   - `port` → `http://localhost:{port}{health.endpoint}`
   - `auto_subdomain` → **не обрабатывается** (метод `_get_health_url` возвращает `None`)

> Если у сервиса только `auto_subdomain` маршрутизация, health check не будет работать. Рекомендуется либо добавить маршрут `domain`/`subfolder`/`port`, либо отключить health check (`enabled: false`).

### 3.4. Видимость и доступ

- **`visibility: internal`** — Caddy применяет snippet `internal_only`, который отклоняет запросы из IP-адресов вне приватных диапазонов (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16) с `403 Access Denied`.
- **`visibility: public`** — сервис доступен из интернета. Caddy автоматически получает SSL-сертификат:
  - `domain` — через Let's Encrypt (ACME HTTP-01 challenge).
  - `auto_subdomain` — через on-demand TLS. Платформа валидирует домен через `GET /api/tls/validate?domain=...`. При первом HTTPS-запросе Caddy обращается к master-сервису для подтверждения, что домен зарегистрирован.

### 3.5. Бэкапы — требования

Если `backup.enabled: true`:

1. **Переменные окружения** `KOPIA_REPOSITORY` и `KOPIA_REPOSITORY_PASSWORD` должны быть установлены в окружении master-сервиса (не в `.env` сервиса).
2. **`backup.paths`** — пути внутри контейнера сервиса (например `/app/data`).
3. **`backup.databases`** — строки подключения к БД для дампа (например `"postgresql://user:pass@host:5432/dbname"`).
4. **`backup.schedule`** — валидное cron-выражение (проверяется через `croniter`).
5. **`backup.storage_type: s3`** — требует `s3_endpoint` и `s3_bucket`.
6. **Модель `extra="forbid"`** — нельзя добавлять неизвестные поля (например `storage_type: sftp` вызовет ошибку валидации).

### 3.6. Локальные переопределения

Для разработки можно создать `service.local.yml` рядом с `service.yml`. Содержимое объединяется с основным манифестом (deep merge: списки заменяются целиком, не объединяются). Файл **не коммитится** (добавить в `.gitignore`).

```yaml
# service.local.yml — пример для локальной разработки
routing:
  - type: subfolder
    base_domain: localhost
    path: /my-service
    internal_port: 3000
    container_name: my-service
```

### 3.7. Чек-лист для выдачи пользователю

ИИ должен сформировать чек-лист вида:

```
✅ Чек-лист требований к сервису <имя>:

□ Docker Compose
  □ Файл docker-compose.yml существует в директории сервиса
  □ Контейнер подключён к внешней сети platform_network
  □ container_name в docker-compose.yml совпадает с container_name в service.yml
  □ Добавлен лейбл "platform.service=<имя-сервиса>" (для logs/status)

□ Сеть
  □ Внешняя сеть platform_network создана (docker network create platform_network)
  □ Caddy и master-сервис уже в этой сети

□ Приложение
  □ Слушает на порту <internal_port> (по умолчанию 8000)
  □ [Если health включён] Отвечает 200 OK на GET <health.endpoint> (по умолчанию /health)

□ Фронтенд-прокси (если nginx/прокси внутри контейнера ходит на бэкенд)
  □ proxy_pass указывает на уникальное имя (container_name), а не на generic-имя compose-сервиса (backend/api/db)
  □ Настроен resolver 127.0.0.11 valid=10s (рантайм-разрешение имён)
  □ Бэкенд-контейнер слушает порт, на который ссылается прокси

□ Маршрутизация
  □ [Если domain] DNS A-запись указывает на IP сервера платформы
  □ [Если auto_subdomain] base_domain резолвится на IP сервера платформы
  □ [Если subfolder] base_domain резолвится на IP сервера платформы

□ Бэкапы (если включены)
  □ Установлены KOPIA_REPOSITORY и KOPIA_REPOSITORY_PASSWORD в окружении master-сервиса
  □ [Если s3] Указаны s3_endpoint и s3_bucket
  □ [Если databases] Строки подключения валидны и доступны из master-контейнера

□ Деплой
  □ Выполнить: platform deploy <имя-сервиса>
  □ Проверить: platform status <имя-сервиса>
  □ Проверить URL: открыть в браузере адрес сервиса
```

---

## 4. Сводная таблица: как система использует каждое поле

| Поле | Где используется | Как |
|---|---|---|
| `name` | Discovery, Caddy templates, Health checker, DockerManager | Идентификатор сервиса, имя директории, auto_subdomain домен (`{name}.{base_domain}`), Caddy logging |
| `display_name` | UI (NiceGUI) | Отображение в интерфейсе |
| `version` | Caddy templates (комментарий) | Информация в сгенерированном конфиге |
| `description` | UI | Отображение в интерфейсе |
| `type` | DockerManager | Выбор метода деплоя (`docker-compose` → `docker compose up -d`) |
| `visibility` | Caddy templates | Если `internal` → импорт snippet `internal_only` (блокировка внешних IP) |
| `routing[].type` | CaddyManager | Выбор шаблона: `domain.caddy.j2`, `subfolder.caddy.j2`, `port.caddy.j2`, `auto_subdomain.caddy.j2` |
| `routing[].domain` | Caddy templates | Адрес site-блока: `{domain} { ... }` |
| `routing[].base_domain` | Caddy templates | Адрес site-блока (subfolder); часть домена (auto_subdomain) |
| `routing[].path` | Caddy templates | Matcher path в subfolder: `path {path}/*` |
| `routing[].port` | Caddy templates | Адрес site-блока: `:{port} { ... }` |
| `routing[].internal_port` | Caddy templates | `reverse_proxy http://{container_name}:{internal_port}` |
| `routing[].container_name` | Caddy templates | `reverse_proxy http://{container_name}:{internal_port}`. Если не указан → `host.docker.internal:{internal_port}` (legacy) |
| `routing[].strip_prefix` | Caddy subfolder template | Если `true` → `header_up X-Forwarded-Prefix {path}` |
| `health.enabled` | Health checker, Caddy templates | Если `true` → Caddy добавляет `health_uri`/`health_interval`; health checker делает запросы |
| `health.endpoint` | Health checker, Caddy templates | URL для GET-запроса и Caddy `health_uri` |
| `health.interval` | Caddy templates | `health_interval` в Caddy reverse_proxy |
| `health.timeout` | Health checker | Таймаут HTTP-запроса (парсится через `_parse_timeout`) |
| `health.retries` | Health checker | Количество попыток перед пометкой unhealthy |
| `backup.*` | BackupConfig (Kopia) | Валидация cron, env-переменных, storage_type |
| `tags` | UI | Фильтрация и категоризация |

---

## 5. Известные ограничения

ИИ должен предупредить пользователя о следующих ограничениях:

1. **Только `docker-compose`** — типы `docker`, `static`, `external` объявлены в моделях, но обработчики не реализованы.
2. **Health check для `auto_subdomain`** — health checker не строит URL для `auto_subdomain` маршрутов. Если нужен health check, добавьте маршрут `domain`/`subfolder`/`port` или отключите проверку.
3. **Health check цикл** — интервал цикла `health_check_loop()` захардкожен в `main.py` (30 секунд), не настраивается через `service.yml`. Поле `health.interval` влияет только на Caddy `health_interval`, не на периодичность проверок master-сервисом.
4. **Бэкапы требуют env** — `KOPIA_REPOSITORY` и `KOPIA_REPOSITORY_PASSWORD` должны быть в окружении master-контейнера, а не в `.env` сервиса.
5. **Нет миграций БД** — схема создаётся через `create_all()` при старте, Alembic не настроен.
6. **Telegram-уведомления** — работают автономно (через `TelegramNotifier` в `main.py`), настройки в `service.yml` игнорируются. Для работы требуются `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_IDS` в окружении master-сервиса.
7. **Лейбл `platform.service`** — DockerManager использует его для поиска контейнеров при `stop`/`restart`/`logs`/`stats`. Генерируемый `docker-compose.yml` не добавляет его автоматически — добавите вручную.
8. **`backup` модель `extra="forbid"`** — нельзя добавлять неизвестные поля (например `storage_type: sftp`). Допустимы только `filesystem` и `s3`.
9. **Docker socket** — master-сервис монтирует `/var/run/docker.sock`, управляет контейнерами на хосте. Сервисы должны быть в той же Docker-сети `platform_network`.
10. **Коллизии DNS-алиасов на `platform_network`** — общая сеть разделяется всеми сервисами платформы; generic-имена compose-сервисов (`backend`, `frontend`, `db`, `api`) могут совпадать с чужими. Docker DNS вернёт случайный из совпавших IP, nginx кеширует его при старте → стабильные `502 Connection refused` на чужой IP. Используйте `container_name` в прокси-конфигах (см. §3.2).

---

## 6. Краткий алгоритм для ИИ

```
1. Прочитать контекст задачи (что за сервис, на каком стеке).

2. Задать вопросы из Шага 1:
   a. Имя, описание, видимость
   b. Тип маршрутизации, домен/порт, внутренний порт, имя контейнера
   c. Health endpoint (есть ли, какой путь)
   d. Бэкапы (нужны ли, что бэкапить, расписание, хранение)
   e. Теги (опционально)

3. Сгенерировать service.yml:
   - Включить только обрабатываемые поля
   - container_name обязателен в каждом routing-объекте
   - retention_days (не retention), databases: [str] (не объекты)
   - type: docker-compose

4. Сгенерировать шаблон docker-compose.yml (или требования к нему):
   - Внешняя сеть platform_network
   - container_name совпадает с routing[].container_name
   - Лейбл platform.service={name}

5. Выдать чек-лист требований (Шаг 3.7).

6. Если backup.enabled — предупредить про KOPIA_REPOSITORY / KOPIA_REPOSITORY_PASSWORD.

7. Если routing только auto_subdomain и health.enabled — предупредить про ограничение health checker.
```
