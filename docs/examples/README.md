# Примеры использования

## Примеры конфигураций различных типов сервисов

### 1. Статический сайт

```yaml
# service.yml
name: landing-page
display_name: "Корпоративный сайт"
version: "1.0.0"
description: "Статический корпоративный сайт"
type: static
visibility: public

routing:
  - type: domain
    domain: company.example.com

health:
  enabled: false

backup:
  enabled: true
  schedule: "0 3 * * *"
  retention: 30
  paths:
    - ./public

logging:
  driver: loki
```

Структура файлов:
```
/apps/services/public/landing-page/
├── service.yml
├── public/
│   ├── index.html
│   ├── css/
│   └── js/
└── Dockerfile
```

### 2. API сервис на FastAPI

```yaml
# service.yml
name: user-api
display_name: "API пользователей"
version: "2.1.0"
description: "Микросервис управления пользователями"
type: docker-compose
visibility: internal

routing:
  - type: subfolder
    base_domain: api.example.com
    path: /users
    internal_port: 8000

health:
  enabled: true
  endpoint: /health
  interval: 30s

resources:
  memory_limit: 1G
  cpu_limit: 1.0

backup:
  enabled: true
  schedule: "0 2 * * *"
  retention: 7
  databases:
    - type: postgres
      container: db
      database: users

logging:
  driver: loki
  labels:
    - service
    - level

dependencies:
  services:
    - postgres
    - redis

environment:
  LOG_LEVEL: info
  DATABASE_URL: postgresql://user:pass@db:5432/users

secrets:
  - DATABASE_URL
  - SECRET_KEY

notifications:
  telegram: true
  events:
    - deploy
    - error
    - health_fail
```

### 3. Микросервис на Node.js

```yaml
# service.yml
name: notification-service
display_name: "Сервис уведомлений"
version: "1.5.2"
description: "Сервис отправки уведомлений пользователям"
type: docker-compose
visibility: internal

routing:
  - type: port
    port: 3005
    internal_port: 3000

health:
  enabled: true
  endpoint: /health
  interval: 15s

resources:
  memory_limit: 256M
  cpu_limit: 0.5

backup:
  enabled: false

logging:
  driver: loki

dependencies:
  external:
    - rabbitmq

environment:
  NODE_ENV: production
  RABBITMQ_URL: amqp://rabbitmq:5672

secrets:
  - RABBITMQ_URL
```

### 4. Сервис с базой данных PostgreSQL

```yaml
# service.yml
name: blog-engine
display_name: "Блог-платформа"
version: "3.0.1"
description: "Платформа для ведения блогов"
type: docker-compose
visibility: public

routing:
  - type: domain
    domain: blog.example.com
    internal_port: 8000

health:
  enabled: true
  endpoint: /health

resources:
  memory_limit: 2G
  cpu_limit: 2.0

backup:
  enabled: true
  schedule: "0 1 * * *"
  retention: 30
  paths:
    - ./media
  databases:
    - type: postgres
      container: postgres
      database: blog

logging:
  driver: loki

dependencies:
  services:
    - postgres
    - redis

environment:
  LOG_LEVEL: info
  DATABASE_URL: postgresql://blog:pass@postgres:5432/blog

secrets:
  - DATABASE_URL
  - SECRET_KEY
```

### 5. Сервис с внешними зависимостями

```yaml
# service.yml
name: analytics-dashboard
display_name: "Аналитическая панель"
version: "1.2.0"
description: "Панель для анализа бизнес-метрик"
type: docker-compose
visibility: internal

routing:
  - type: subfolder
    base_domain: internal.example.com
    path: /analytics
    internal_port: 3000

health:
  enabled: true
  endpoint: /api/health

resources:
  memory_limit: 1G
  cpu_limit: 1.5

backup:
  enabled: true
  schedule: "0 4 * * *"
  retention: 90
  paths:
    - ./reports

logging:
  driver: loki

dependencies:
  services:
    - postgres
  external:
    - keycloak
    - elasticsearch

environment:
  LOG_LEVEL: warn
  KEYCLOAK_URL: https://auth.example.com
  ES_URL: https://es.example.com

secrets:
  - DATABASE_URL
  - KEYCLOAK_CLIENT_SECRET
```

## Примеры сложной маршрутизации

### Множественные маршруты для одного сервиса

```yaml
# service.yml
name: multi-route-app
display_name: "Многофункциональное приложение"
version: "1.0.0"
description: "Приложение с API и админкой на разных путях"
type: docker-compose
visibility: public

routing:
  # Основной API
  - type: domain
    domain: api.multi.example.com
    internal_port: 8000
    
  # Админка
  - type: domain
    domain: admin.multi.example.com
    internal_port: 8001
    
  # Общая точка доступа
  - type: subfolder
    base_domain: apps.example.com
    path: /multi
    internal_port: 8000

health:
  enabled: true
  endpoint: /health

backup:
  enabled: true
  schedule: "0 2 * * *"
  retention: 7

logging:
  driver: loki
```

### Внутренний и внешний доступ к одному сервису

```yaml
# service.yml
name: hybrid-service
display_name: "Гибридный сервис"
version: "1.3.0"
description: "Сервис с открытым API и закрытой админкой"
type: docker-compose
visibility: public

routing:
  # Публичный API
  - type: domain
    domain: api.service.example.com
    internal_port: 8000
    
  # Внутренняя админка
  - type: subfolder
    base_domain: internal.example.com
    path: /service-admin
    internal_port: 8001

health:
  enabled: true
  endpoint: /health

backup:
  enabled: true
  schedule: "0 2 * * *"
  retention: 14

logging:
  driver: loki
```

## Примеры конфигурации бэкапов для разных сценариев

### 1. Бэкап только файлов

```yaml
# service.yml
name: file-storage
display_name: "Файловое хранилище"
version: "1.0.0"
description: "Сервис хранения пользовательских файлов"
type: docker-compose
visibility: internal

routing:
  - type: subfolder
    base_domain: internal.example.com
    path: /files
    internal_port: 8080

health:
  enabled: true
  endpoint: /health

backup:
  enabled: true
  schedule: "0 */6 * * *"  # Каждые 6 часов
  retention: 7
  paths:
    - ./uploads
    - ./documents

logging:
  driver: loki
```

### 2. Бэкап базы данных PostgreSQL

```yaml
# service.yml
name: db-service
display_name: "Сервис с базой данных"
version: "1.0.0"
description: "Сервис с критичной базой данных"
type: docker-compose
visibility: internal

routing:
  - type: port
    port: 8082
    internal_port: 8000

health:
  enabled: true
  endpoint: /health

backup:
  enabled: true
  schedule: "0 1 * * *"  # Каждую ночь
  retention: 30
  databases:
    - type: postgres
      container: postgres
      database: critical_data

logging:
  driver: loki
```

### 3. Комбинированный бэкап (файлы + база данных)

```yaml
# service.yml
name: ecommerce-platform
display_name: "Платформа электронной коммерции"
version: "2.5.0"
description: "Платформа для интернет-магазина"
type: docker-compose
visibility: public

routing:
  - type: domain
    domain: shop.example.com
    internal_port: 3000

health:
  enabled: true
  endpoint: /api/health

backup:
  enabled: true
  schedule: "0 0 * * *"  # Каждую ночь
  retention: 90
  paths:
    - ./product-images
    - ./user-uploads
  databases:
    - type: postgres
      container: db
      database: shop

logging:
  driver: loki
```

### 4. Инкрементальный бэкап с коротким сроком хранения

```yaml
# service.yml
name: cache-service
display_name: "Кэширующий сервис"
version: "1.1.0"
description: "Сервис кэширования с быстрыми бэкапами"
type: docker-compose
visibility: internal

routing:
  - type: port
    port: 6380
    internal_port: 6379

health:
  enabled: true
  endpoint: /ping

backup:
  enabled: true
  schedule: "*/30 * * * *"  # Каждые 30 минут
  retention: 1  # Хранить только 1 день
  paths:
    - ./cache

logging:
  driver: loki