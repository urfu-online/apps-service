# Конфигурация Caddy

Руководство по настройке и управлению Caddy в качестве reverse proxy для платформы.

## Обзор

Caddy используется как reverse proxy для маршрутизации трафика к сервисам платформы. Конфигурация генерируется автоматически на основе манифестов сервисов (`service.yml`).

## Переменные окружения

### PLATFORM_DOMAIN

Основной домен платформы задаётся через переменную `PLATFORM_DOMAIN`. По умолчанию используется `localhost` для разработки.

```bash
# Продакшен
echo "PLATFORM_DOMAIN=apps.urfu.online" > .env

# Локальная разработка
echo "PLATFORM_DOMAIN=localhost" > .env
```

Переменная передаётся в контейнер Caddy через `docker-compose.yml`:

```yaml
environment:
  - PLATFORM_DOMAIN=${PLATFORM_DOMAIN:-localhost}
```

### APP_ENV

Для условного включения конфигураций разработки используется `APP_ENV`:

- `prod` (по умолчанию) — продакшен с автоматическим HTTPS
- `dev` — разработка с отключённым авто-HTTPS

```yaml
environment:
  - APP_ENV=${APP_ENV:-prod}
  - PLATFORM_DOMAIN=${PLATFORM_DOMAIN:-localhost}
```

## Конфигурационные файлы

| Файл | Описание |
|------|----------|
| `_core/caddy/Caddyfile` | Глобальные настройки и импорт конфигураций |
| `_core/caddy/conf.d/*.caddy` | Автоматически генерируемые конфиги сервисов |
| `_core/caddy/development.caddy` | Конфигурации для локальной разработки |
| `_core/caddy/templates/` | Jinja2-шаблоны для генерации конфигов |

## Различия между окружениями

| Параметр | Продакшен (`prod`) | Разработка (`dev`) |
|----------|-------------------|-------------------|
| HTTPS | Автоматический SSL | Отключён |
| Редиректы HTTP→HTTPS | Включены | Нет |
| Development routes | Нет | Да (localhost, instructor.*) |

## Управление конфигурацией

### Перезагрузка через API

```bash
curl -X POST http://localhost:2019/load \
  -H "Content-Type: application/json" \
  -d @/path/to/new/Caddyfile
```

### Перезапуск контейнера

```bash
docker compose -f _core/caddy/docker-compose.yml restart caddy
```

### Проверка конфигурации

```bash
docker compose -f _core/caddy/docker-compose.yml exec caddy \
  caddy validate --config /etc/caddy/Caddyfile
```

## Требования к сервисам

- Все сервисы должны иметь `service.yml` с полем `health_check.endpoint`
- Внутренние сервисы (`services/internal/`) не проксируются наружу
- Генерация конфигов — через `CaddyManager` в Master Service

## См. также

- [Master Service](master-service.md) — основная документация по сервису
- [Архитектура Caddy](../architecture/caddy.md) — детали интеграции
