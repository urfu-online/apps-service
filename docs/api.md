# Документация API

!!! warning "Аутентификация"
    Все эндпоинты требуют `Authorization: Bearer <token>`.
    **Login endpoint в API отсутствует.** Токен получается через внешний Keycloak или напрямую через builtin auth (SQLite user ID).

## Общее описание

API Master Service предоставляет интерфейс для управления сервисами платформы, включая развертывание, мониторинг, управление логами и резервными копиями. API следует RESTful принципам и возвращает данные в формате JSON.

### Базовый URL
```
http://localhost:8000/api
```

### Форматы данных
- **Запросы**: JSON
- **Ответы**: JSON
- **Кодировка**: UTF-8

## 2. Аутентификация и авторизация

API использует Keycloak для аутентификации и авторизации. Для доступа к защищенным эндпоинтам необходимо предоставить действующий JWT токен в заголовке Authorization.

### Получение токена

Для получения токена необходимо выполнить запрос к Keycloak серверу:

```http
POST /auth/realms/{realm}/protocol/openid-connect/token
Content-Type: application/x-www-form-urlencoded

grant_type=password&client_id={client_id}&username={username}&password={password}
```

### Использование токена

После получения токена, его необходимо передавать в заголовке всех запросов к API:

```http
Authorization: Bearer {access_token}
```

## 3. Эндпоинты для управления сервисами

### Получение списка сервисов

```http
GET /services
```

**Параметры запроса:**
- `visibility` (опционально): фильтр по видимости (`public`, `internal`)
- `status` (опционально): фильтр по статусу (`running`, `stopped`, `error`)

**Пример ответа:**
```json
[
  {
    "name": "my-service",
    "display_name": "My Service",
    "version": "1.0.0",
    "status": "running",
    "visibility": "public",
    "type": "docker-compose"
  }
]
```

### Получение детальной информации о сервисе

```http
GET /services/{service_name}
```

**Пример ответа:**
```json
{
  "manifest": {
    "name": "my-service",
    "display_name": "My Service",
    "version": "1.0.0",
    "description": "Service description",
    "type": "docker-compose",
    "visibility": "public",
    "status": "running"
  },
  "stats": {
    "container_name": {
      "cpu_percent": 12.5,
      "memory_usage_mb": 128.5,
      "memory_limit_mb": 512,
      "memory_percent": 25.1,
      "status": "running"
    }
  }
}
```

### Деплой/редеплой сервиса

```http
POST /services/{service_name}/deploy
```

**Тело запроса:**
```json
{
  "build": true,
  "pull": false
}
```

**Пример ответа:**
```json
{
  "success": true,
  "message": "Service deployed successfully",
  "logs": [
    "Building image...",
    "Starting containers...",
    "Service is running"
  ]
}
```

### Остановка сервиса

```http
POST /services/{service_name}/stop
```

**Пример ответа:**
```json
{
  "success": true,
  "message": "Service stopped"
}
```

### Перезапуск сервиса

```http
POST /services/{service_name}/restart
```

**Пример ответа:**
```json
{
  "success": true,
  "message": "Service restarted"
}
```

## 4. Эндпоинты для работы с логами

### Получение логов сервиса

```http
GET /logs/service/{service_name}
```

**Параметры запроса:**
- `tail` (опционально): количество последних строк (по умолчанию 100)
- `since` (опционально): время начала выборки (ISO 8601)

**Пример ответа:**
```json
[
  "2023-01-01T10:00:00Z [INFO] Service started",
  "2023-01-01T10:01:00Z [INFO] Processing request",
  "2023-01-01T10:02:00Z [ERROR] Connection timeout"
]
```

### Поиск по логам сервиса

```http
POST /logs/service/{service_name}/search
```

**Тело запроса:**
```json
{
  "query": "error",
  "limit": 50
}
```

**Пример ответа:**
```json
[
  "2023-01-01T10:02:00Z [ERROR] Connection timeout",
  "2023-01-01T10:05:00Z [ERROR] Database connection failed"
]
```

## 5. Эндпоинты для работы с бэкапами

### Создание бэкапа

```http
POST /backups/service/{service_name}/backup
```

**Тело запроса:**
```json
{
  "reason": "manual"
}
```

**Пример ответа:**
```json
{
  "id": 0,
  "service_id": 0,
  "name": "my-service_20230101_100000",
  "timestamp": "2023-01-01T10:00:00Z",
  "size": null,
  "status": "completed",
  "reason": "manual"
}
```

### Получение списка бэкапов

```http
GET /backups/service/{service_name}
```

**Параметры запроса:**
- `skip` (опционально): количество пропущенных записей (по умолчанию 0)
- `limit` (опционально): максимальное количество записей (по умолчанию 100)

**Пример ответа:**
```json
[
  {
    "id": 0,
    "service_id": 0,
    "name": "my-service_20230101_100000",
    "timestamp": "2023-01-01T10:00:00Z",
    "size": null,
    "status": "completed",
    "reason": "manual"
  }
]
```

### Восстановление из бэкапа

```http
POST /backups/service/{service_name}/restore
```

**Тело запроса:**
```json
{
  "backup_id": 1
}
```

**Пример ответа:**
```json
{
  "message": "Restore scheduled for service my-service",
  "backup_id": 1
}
```

## 6. Эндпоинты для проверки состояния

### Проверка состояния платформы

```http
GET /health
```

**Пример ответа:**
```json
{
  "overall_status": "healthy",
  "services": [
    {
      "service_name": "my-service",
      "is_healthy": true,
      "response_time": 0.123,
      "last_checked": "2023-01-01T10:00:00Z",
      "error": null
    }
  ],
  "timestamp": "2023-01-01T10:00:00Z"
}
```

### Получение состояния здоровья конкретного сервиса

```http
GET /health/service/{service_name}
```

**Пример ответа:**
```json
{
  "service_name": "my-service",
  "is_healthy": true,
  "response_time": 0.123,
  "last_checked": "2023-01-01T10:00:00Z",
  "error": null
}
```

## 7. Форматы запросов и ответов

### Общие принципы

- Все эндпоинты возвращают данные в формате JSON
- Даты и временные метки представлены в формате ISO 8601
- Все ответы содержат поля `success` и `message` для индикации результата операции

### Стандартные поля ответов

```json
{
  "success": true,
  "message": "Operation completed successfully",
  "data": {}
}
```

## 8. Коды ошибок

### HTTP статусы

- `200 OK` - Запрос успешно выполнен
- `201 Created` - Ресурс успешно создан
- `400 Bad Request` - Некорректный запрос
- `401 Unauthorized` - Неавторизованный доступ
- `403 Forbidden` - Доступ запрещен
- `404 Not Found` - Ресурс не найден
- `500 Internal Server Error` - Внутренняя ошибка сервера

### Стандартный формат ошибок

```json
{
  "detail": "Error description"
}