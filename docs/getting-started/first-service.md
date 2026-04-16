# Первый сервис

> ⚠️ **Важно:** В разделе `routing` всегда указывайте `container_name` — имя Docker-контейнера, к которому Caddy должен проксировать запросы. Без этого поля Caddy будет пытаться проксировать на хост-машину (`host.docker.internal`), что создаёт конфликты портов и проблемы с безопасностью. Имя контейнера должно совпадать с `container_name` в `docker-compose.yml`.

Сервис в платформе — это директория с двумя файлами: `service.yml` (манифест) и `docker-compose.yml`.

## Быстрый способ

```bash
platform new my-app public
```

Создаст структуру в `services/public/my-app/`:

```
services/public/my-app/
├── service.yml          # Манифест: имя, роутинг, health, backup
├── docker-compose.yml   # Docker-контейнеры сервиса
├── .env.example         # Пример переменных окружения
└── README.md            # Документация сервиса
```

## Ручной способ

Создайте `services/public/my-app/service.yml`:

```yaml
name: my-app
display_name: "Моё приложение"
version: "1.0.0"
description: "Мой первый сервис на платформе"
type: docker-compose
visibility: public

# Автоматический поддомен (стандартное поведение)
routing:
  - auto_subdomain: true
    base_domain: apps.urfu.online
    internal_port: 80
    container_name: my-app

health:
  enabled: true
  endpoint: /
  interval: 30s
  timeout: 10s
  retries: 3

backup:
  enabled: false
```

И `services/public/my-app/docker-compose.yml`:

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

## Деплой

```bash
# Перезапустить core (если первый раз)
./restart_core.sh --build

# Запустить сервис
platform deploy my-app

# Проверить
platform list
```

Сервис появится:
- ✅ В UI Master Service (`http://localhost:8001`)
- ✅ В роутинге Caddy с автоподдоменом `https://my-app.apps.urfu.online`
- ✅ С автоматическим SSL-сертификатом (выпускается при первом запросе)
- ✅ В health check мониторинге (каждые 30s)

## Как работают автоподдомены

Платформа автоматически назначает каждому публичному сервису поддомен вида `{service-name}.apps.urfu.online`:

1. При деплое CaddyManager генерирует конфиг для поддомена
2. При первом HTTPS-запросе Caddy выполняет ACME challenge
3. Платформа валидирует домен через `/api/tls/validate`
4. Caddy выпускает SSL-сертификат автоматически

Вам не нужно настраивать DNS или заказывать сертификаты — всё работает из коробки.

## Свой домен (опционально)

Если нужен кастомный домен вместо автоподдомена:

```yaml
routing:
  - type: domain
    domain: myapp.example.com
    internal_port: 80
    container_name: my-app
```

При использовании своего домена:
1. Настройте DNS A-запись на IP сервера
2. Caddy автоматически получит SSL-сертификат через Let's Encrypt

## Local override

Хотите поменять настройки только для локальной разработки, не трогая основной `service.yml`?

Создайте `services/public/my-app/service.local.yml`:

```yaml
routing:
  - type: port
    internal_port: 80
    port: 9090
    container_name: my-app  # ⚠️ Должно совпадать с основным service.yml

health:
  interval: 10s
```

Платформа автоматически смержит `service.local.yml` поверх `service.yml`. Файл в `.gitignore` — не попадёт в коммит.

## Что дальше

- [Управление сервисами](../user-guide/services.md) — все команды CLI
- [Типы роутинга](../user-guide/services.md) — автодомен, свой домен, подпапка, порт
- [Примеры](../examples.md) — готовые конфиги для разных типов сервисов
