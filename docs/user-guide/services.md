# Руководство по созданию и управлению сервисами

> ⚠️ **Важно:** В разделе `routing` всегда указывайте `container_name` — имя Docker-контейнера, к которому Caddy должен проксировать запросы. Без этого поля Caddy будет проксировать на хост-машину (`host.docker.internal`), что создаёт конфликты портов и проблемы с безопасностью.

Это руководство описывает процесс создания и управления сервисами на платформе. Платформа предоставляет централизованный подход к управлению различными типами сервисов с минимальным участием DevOps.

## 1. Создание нового сервиса с использованием шаблонов

Для создания нового сервиса используется CLI утилита platform:

```bash
# Создание нового сервиса
platform new my-service public

# Или для внутреннего сервиса
platform new internal-service internal
```

Эта команда создаст структуру директорий в соответствующей папке (`/opt/platform/services/public/` или `/opt/platform/services/internal/`) со следующими файлами:

- `service.yml` - манифест сервиса
- `docker-compose.yml` - конфигурация Docker Compose
- `.env` - файл переменных окружения (не коммитится)
- `README.md` - документация сервиса

После создания шаблона, вы можете:

1. Настроить манифест `service.yml` под ваши требования
2. Добавить ваш код приложения в директорию сервиса
3. Настроить `docker-compose.yml` при необходимости
4. Добавить переменные окружения в `.env`

## 2. Описание структуры манифеста service.yml

Манифест `service.yml` - это основной конфигурационный файл сервиса, который описывает все его параметры:

```yaml
# === МЕТАДАННЫЕ ===
name: my-service
display_name: "Мой Сервис"
version: "1.0.0"
description: "Краткое описание сервиса"
maintainer: "team@example.com"
repository: "https://github.com/org/my-service"
tags:
  - web
  - production

# === ТИП СЕРВИСА ===
type: docker-compose  # docker-compose | docker | static | external

# === ВИДИМОСТЬ ===
visibility: public    # public | internal

# === МАРШРУТИЗАЦИЯ ===
routing:
  # Вариант 1: Отдельный домен
  - type: domain
    domain: myservice.example.com
    internal_port: 8000
    container_name: my-service  # ⚠️ Обязательно: имя Docker-контейнера

  # Вариант 2: Подпапка
  - type: subfolder
    base_domain: apps.example.com
    path: /my-service
    strip_prefix: true  # убирать prefix при проксировании
    internal_port: 8000
    container_name: my-service  # ⚠️ Обязательно: имя Docker-контейнера

  # Вариант 3: Порт (внутренний/тестовый)
  - type: port
    port: 8081
    internal_port: 8000
    container_name: my-service  # ⚠️ Обязательно: имя Docker-контейнера

  # Дополнительные заголовки
  headers:
    X-Service-Name: my-service

# === HEALTH CHECK ===
health:
  enabled: true
  endpoint: /health
  interval: 30s
  timeout: 10s
  retries: 3

# === РЕСУРСЫ ===
resources:
  memory_limit: 512M
  cpu_limit: 0.5

# === БЭКАПЫ ===
backup:
  enabled: true
  schedule: "0 2 * * *"  # Каждый день в 2:00
  retention: 7           # Хранить 7 дней
  paths:
    - ./data
    - ./uploads
  databases:
    - type: postgres
      container: db
      database: myservice

# === ЛОГИРОВАНИЕ ===
logging:
  driver: loki
  labels:
    - service
    - level

# === ЗАВИСИМОСТИ ===
dependencies:
  services:
    - postgres
    - redis
  external:
    - keycloak

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ (дефолты) ===
environment:
  LOG_LEVEL: info
  
# === СЕКРЕТЫ (ссылки) ===
secrets:
  - DATABASE_URL
  - API_KEY
  
# === ХУКИ ===
hooks:
  post_deploy:
    - "./scripts/migrate.sh"
  pre_backup:
    - "./scripts/prepare-backup.sh"

# === УВЕДОМЛЕНИЯ ===
notifications:
  telegram: true
  events:
    - deploy
    - error
    - health_fail
```

## 3. Настройка маршрутизации (домен, подпапка, порт)

Платформа поддерживает три типа маршрутизации.

!!! warning "`container_name` обязателен для всех сервисов"
    Без `container_name` Caddy проксирует на `host.docker.internal:<port>` — на хост-машину.
    Это legacy-режим: обход SSL, auth, rate limit; конфликты портов; дырка в безопасности.
    **Указывайте `container_name` всегда.** Имя должно совпадать с контейнером в `docker-compose.yml`.

### Отдельный домен

```yaml
routing:
  - type: domain
    domain: myservice.example.com
    internal_port: 8000
```

Сервис будет доступен по адресу `https://myservice.example.com`.

### Подпапка

```yaml
routing:
  - type: subfolder
    base_domain: apps.example.com
    path: /my-service
    strip_prefix: true
    internal_port: 8000
```

Сервис будет доступен по адресу `https://apps.example.com/my-service`.

### Порт

```yaml
routing:
  - type: port
    port: 8081
    internal_port: 8000
```

Сервис будет доступен по адресу `https://apps.example.com:8081`.

## 4. Конфигурация бэкапов для сервиса

Настройка бэкапов осуществляется в разделе `backup` манифеста:

```yaml
backup:
  enabled: true
  schedule: "0 2 * * *"  # Каждый день в 2:00
  retention: 7           # Хранить 7 дней
  paths:
    - ./data
    - ./uploads
  databases:
    - type: postgres
      container: db
      database: myservice
```

Для создания бэкапа вручную используйте CLI:

```bash
platform backup my-service
```

## 5. Управление зависимостями сервиса

Зависимости сервиса указываются в разделе `dependencies`:

```yaml
dependencies:
  services:
    - postgres
    - redis
  external:
    - keycloak
```

Платформа автоматически обеспечит запуск зависимостей перед запуском основного сервиса.

## 6. Работа с переменными окружения и секретами

Переменные окружения определяются в разделе `environment`:

```yaml
environment:
  LOG_LEVEL: info
  DATABASE_HOST: postgres
```

Секреты указываются в разделе `secrets`:

```yaml
secrets:
  - DATABASE_URL
  - API_KEY
```

Секреты хранятся в защищенном хранилище и передаются в контейнеры через механизм секретов Docker.

## 7. Деплой, остановка и перезапуск сервисов

### Деплой сервиса

```bash
# Деплой сервиса
platform deploy my-service

# Деплой с пересборкой образов
platform deploy my-service --build

# Деплой с обновлением образов
platform deploy my-service --pull
```

### Остановка сервиса

```bash
platform stop my-service
```

### Перезапуск сервиса

```bash
platform restart my-service
```

## 8. Мониторинг состояния сервисов

Для просмотра состояния всех сервисов используйте:

```bash
platform status
```

Также можно получить статус конкретного сервиса:

```bash
platform status my-service
```

Платформа автоматически проверяет здоровье сервисов и отправляет уведомления в Telegram при проблемах.

## 9. Работа с логами сервисов

Для просмотра логов сервиса используйте:

```bash
# Просмотр последних 100 строк логов
platform logs my-service

# Просмотр последних 50 строк логов
platform logs my-service 50
```

Логи автоматически собираются и отправляются в систему Loki для централизованного хранения.

## 10. Использование CLI утилиты platform

CLI утилита `platform` предоставляет удобный интерфейс для управления сервисами:

```bash
# Создание нового сервиса
platform new <name> [visibility]

# Деплой сервиса
platform deploy <service> [--build] [--pull]

# Остановка сервиса
platform stop <service>

# Перезапуск сервиса
platform restart <service>

# Просмотр логов
platform logs <service> [lines]

# Просмотр статуса
platform status [service]

# Создание бэкапа
platform backup <service>
```

Платформа также предоставляет веб-интерфейс для управления сервисами по адресу `https://platform.yourdomain.com`.