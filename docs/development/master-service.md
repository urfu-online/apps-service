# Master Service — руководство разработчика

Документация для разработки **Master Service** (`_core/master/`) — центрального сервиса платформы на FastAPI + NiceGUI.

## Структура сервиса

```
_core/master/
├── app/
│   ├── api/                # REST API endpoints
│   │   └── routes/         # services, deployments, logs, backups, health, users
│   ├── core/               # Ядро: БД, события, безопасность
│   │   ├── database.py     # SQLAlchemy, создание таблиц
│   │   ├── events.py       # EventBus (pub/sub)
│   │   └── security.py     # Keycloak + Builtin auth
│   ├── models/             # SQLAlchemy модели
│   ├── services/           # Бизнес-логика
│   │   ├── discovery.py    # ServiceDiscovery (сканирование сервисов)
│   │   ├── caddy_manager.py# Генерация Caddy конфигов
│   │   ├── docker_manager.py# Deploy/stop/restart
│   │   ├── health_checker.py# HTTP health checks
│   │   ├── backup_manager.py# Бэкапы (rsync, pg_dump)
│   │   ├── log_manager.py  # Логи (заглушка)
│   │   └── notifier.py     # Telegram уведомления
│   ├── ui/                 # NiceGUI интерфейс
│   ├── config.py           # Настройки (pydantic-settings)
│   └── main.py             # Точка входа, lifespan, background tasks
├── tests/
│   ├── unit/               # Модульные тесты
│   └── integration/        # Интеграционные тесты
├── test-fixtures/          # Фикстуры для тестов
├── docker-compose.yml      # Production
├── docker-compose.dev.yml  # Dev (hot reload)
├── docker-compose.test.yml # Test (pytest в контейнере)
├── Dockerfile
├── Makefile
├── pyproject.toml          # Poetry
└── pytest.ini
```

## Зависимости

### Установка Poetry

https://python-poetry.org/docs/#installation

### Установка зависимостей

```bash
cd _core/master
poetry install             # основные
poetry install --with dev  # + тесты
```

### Виртуальное окружение

```bash
poetry shell               # активировать
poetry run pytest          # или запуск без активации
```

## Тесты

```bash
poetry run test                       # все тесты
poetry run pytest tests/unit/         # юнит-тесты
poetry run pytest tests/integration/  # интеграционные
poetry run pytest --cov=app           # с покрытием
poetry run pytest --cov=app --cov-report=html  # HTML-отчёт → htmlcov/
```

## Docker

### Сборка

```bash
docker build -t apps-core-master .                    # production
docker build --build-arg BUILD_ENV=dev -t master:dev .  # dev
```

### Запуск

```bash
docker compose up -d                                            # production
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d  # dev
docker compose -f docker-compose.yml -f docker-compose.test.yml up --build  # test
```

## Makefile

```bash
make test       # pytest
make test-cov   # pytest --cov=app
make test-html  # pytest --cov + открыть HTML-отчёт
```

## API

После запуска:
- API → `http://localhost:8000/api/`
- Swagger → `http://localhost:8000/docs`
- ReDoc → `http://localhost:8000/redoc`

Порт 8000 маппится на 8001 контейнера (`8001:8000`).

## БД

SQLite по умолчанию (`master.db`). При старте `create_all()` создаёт таблицы.

Миграций пока нет — см. [issue #21](https://github.com/urfu-online/apps-service/issues/21).

Сброс: `rm master.db`

## Отладка

```bash
DEBUG=true  # переменная окружения
```

Логи — в stdout контейнера:
```bash
docker logs platform-master --tail 50 -f
```

## Настройка Caddy

Caddy используется как reverse proxy. Подробная документация: [caddy-configuration.md](caddy-configuration.md)
