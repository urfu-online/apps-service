# CLI и UI

Платформа предоставляет терминальный CLI (`platform`) и веб-интерфейс (NiceGUI).

## Platform CLI

Python CLI на Typer. Установка:

```bash
cd _core/platform-cli && ./install.sh
```

| Команда | Описание |
|---|---|
| `platform list` | Сервисы со статусом (Rich-таблица) |
| `platform new <name> [public\|internal]` | Создать сервис из шаблона |
| `platform deploy <svc> [--build] [--pull]` | Деплой |
| `platform stop <svc>` | Остановка |
| `platform restart <svc>` | Перезапуск |
| `platform logs <svc> [-f] [-n N]` | Логи |
| `platform status [<svc>]` | Статус + метрики Docker |
| `platform backup <svc>` | Запустить бэкап (через Master API) |
| `platform reload` | Перезагрузить Caddy |
| `platform info` | Общая информация о платформе |

## Веб-интерфейс (NiceGUI)

Master Service запускает UI на порту **8001** (маппинг `8001:8000`):

```
http://localhost:8001
```

### Страницы

| Страница | Что показывает |
|---|---|
| **Главная** (`/`) | Сводка: кол-во сервисов, статус, типы |
| **Сервисы** (`/services`) | Таблица с фильтрами |
| **Логи** (`/logs`) | Фильтрация по сервису, времени, поиск |
| **Бэкапы** (`/backups`) | Список бэкапов; restore/delete — заглушки |

Детальная страница сервиса (`/services/{name}`) — редирект на `/services`.

### Аутентификация

| Режим | Как войти |
|---|---|
| **Builtin** | Логин/пароль из SQLite (по умолчанию в docker-compose) |
| **Keycloak** | OAuth2 redirect (нужен внешний Keycloak) |

## API

FastAPI API доступно на `http://localhost:8000`:

- **Swagger UI** → `/docs`
- **ReDoc** → `/redoc`
- **Базовый путь API** → `/api/`

!!! warning "Аутентификация в API"
    Все эндпоинты требуют Bearer-токен. Endpoints для login/token issuance **нет** — токен нужно получать externally (Keycloak напрямую или через builtin auth напрямую).
