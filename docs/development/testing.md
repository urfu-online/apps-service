# Тестирование платформы

Трёхуровневая система тестирования для безопасного обновления без риска для production.

## [UPDATED] Текущий статус тестов (апрель 2026)

### Level 0: Unit-тесты
- **Статус**: 104 passed, 9 failed (67% coverage)
- **Проблемы**: 
  - Тесты BuiltInAuthProvider падают из-за проблем с моками БД
  - Некоторые SharedModelTests требуют дополнительных фикстур
- **Команда**: `pytest tests/unit -v --cov`

### Level 1: Интеграционные тесты
- **Статус**: 10 passed, 1 error, 1 skipped
- **Проблемы**:
  - `test_nicegui_ui.py` требует playwright (не установлен)
  - `test_user_crud_integration` использует устаревший AsyncClient API
- **Команда**: `pytest tests/integration -k "not nicegui" -v`

### Level 2: DinD (Docker-in-Docker)
- **Статус**: Требует настройки
- **Проблемы**:
  - Каталоги `services/public` и `services/internal` пусты
  - Требуется копирование тестовых сервисов из `infra/test-env/test-services/`
- **Команда**: См. инструкции ниже

## Уровни тестирования

### Level 0: Unit-тесты (~5 сек)

Изолированные тесты компонентов с моками. Покрывают модели, auth providers, endpoints.

```bash
# Локально (нужны зависимости)
cd _core/master
pytest tests/unit -v

# С покрытием
pytest tests/unit -v --cov=app --cov-report=term-missing
```

**Что проверяет:**
- Модели: User, Role, Service, Deployment, Backup
- Auth providers: BuiltInAuthProvider, KeycloakAuthProvider
- Endpoints: /api/users/*, /services/*, /logs/*, /backups/*, /deployments/*, /tls/*

### Level 1: Интеграционные тесты (~10 сек)

Тестируют ключевые компоненты с моками: ServiceDiscovery, CaddyManager, DockerManager (dry-run).

```bash
# Локально
cd _core/master
pytest tests/integration -v

# Через Docker Compose (полная изоляция)
cd _core/master
docker compose -f docker-compose.yml -f docker-compose.test.yml up --build
```

**Что проверяет:**
- Обнаружение сервисов (public/internal)
- Local override (`service.local.yml`) — merge и обработка ошибок
- Fallback на docker-compose.yml без service.yml
- Генерация Caddy конфигов (domain, subfolder, port routing)
- DockerManager dry-run режим (без реального Docker)

### Level 2: Dry-run режим (~30 сек)

Полный цикл деплоя без реального выполнения — только валидация команд.

```bash
# Через pytest (рекомендуется)
cd _core/master
pytest tests/integration/test_full_deploy_cycle.py::TestDockerManagerDryRun -v

# Или через Python API (для отладки)
python3 -c "
import asyncio
from app.services.docker_manager import DockerManager
from unittest.mock import AsyncMock

async def test():
    manager = DockerManager(AsyncMock())
    result = await manager.deploy_service(manifest, dry_run=True)
    print(result['logs'])

asyncio.run(test())
"
```

### Level 3: DinD VM (~30 сек)

Полноценная изолированная среда через Docker-in-Docker. Симулирует production сервер (`/apps`).

**[UPDATED] Предварительная настройка:**
```bash
# Копирование тестовых сервисов (требуется один раз)
cp -r infra/test-env/test-services/public/* services/public/ 2>/dev/null || true
cp -r infra/test-env/test-services/internal/* services/internal/ 2>/dev/null || true

# Проверка структуры
ls -la services/public/
ls -la services/internal/
```

```bash
# Запуск DinD окружения
cd infra/test-env
docker compose up -d

# Запуск полного цикла тестов
docker compose exec test-env ./test_full_cycle.sh

# Очистка
docker compose down -v
```

**Что проверяет:**
- Структуру проекта и конфиги
- Реальный деплой docker compose
- Caddy шаблоны
- Local override механизмы
- Cleanup ресурсов

## Структура файлов

```
_core/master/
  tests/
    conftest.py                          # Фикстуры (mocks, fixtures)
    unit/
      test_user_models.py                # Level 0: модели пользователей
      test_service_model.py              # Level 0: модели сервисов
      test_deployment_model.py           # Level 0: модели деплоев
      test_auth_endpoints.py             # Level 0: auth provider тесты
      test_auth_switching.py             # Level 0: переключение провайдеров
      test_user_endpoints.py             # Level 0: /api/users/*
      test_service_endpoints.py          # Level 0: /services/*
      test_log_endpoints.py              # Level 0: /logs/*
      test_backup_endpoints.py           # Level 0: /backups/*
      test_deployment_endpoints.py       # Level 0: /deployments/*
      test_tls_endpoints.py              # Level 0: /tls/*
    integration/
      test_full_deploy_cycle.py          # Level 1: интеграционные тесты
  test-fixtures/                         # Тестовые данные
    services/public/test-web-app/        #   сервисы с service.yml
    services/internal/test-api/
    caddy/templates/                     #   Caddy шаблоны

infra/test-env/
  Dockerfile                             # DinD образ
  docker-compose.yml                     #   DinD compose
  test-services/                         #   тестовые сервисы для DinD
  test_full_cycle.sh                     #   скрипт полного цикла
```

## Фикстуры (conftest.py)

| Фикстура | Назначение |
|----------|------------|
| `test_fixtures_path` | Пути к тестовым данным |
| `mock_docker_client` | Мок Docker SDK |
| `mock_docker_compose` | Мок docker compose команды |
| `mock_notifier` | Мок Telegram нотификатора |
| `mock_aiohttp_session` | Мок aiohttp для Caddy API |
| `sample_service_manifest` | Типичный ServiceManifest |
| `mock_discovery` | Преднастроенный ServiceDiscovery |
| `app_with_mock_discovery` | FastAPI app с моками |

## Стратегия тестирования

| Сценарий | Минимальный уровень | Обязательные тесты |
|----------|---------------------|-------------------|
| Bug fix | Unit | Затронутый модуль |
| New feature | Unit + Integration | Все новые функции |
| Breaking change | All levels | Full suite + DinD |
| Release candidate | All levels + manual | 100% на critical paths |

## [UPDATED] Целевое покрытие

| Компонент | Целевое | Текущее (апрель 2026) |
|-----------|---------|----------------------|
| Critical paths (deploy, discovery, caddy) | 90% | ~35% |
| Models | 80% | ~95% |
| Endpoints | 70% | ~50% |
| **Overall** | **60%** | **67%** |

**Текущее покрытие (pytest --cov):**
- `app/core/security.py`: 83% ✓
- `app/models/`: 90-98% ✓
- `app/services/discovery.py`: 35% ⚠️
- `app/services/docker_manager.py`: 17% ⚠️
- `app/services/backup_manager.py`: 14% ⚠️

## [TODO: требует проверки] Известные проблемы

1. **Тесты BuiltInAuthProvider** - моки БД не работают правильно, требуется рефакторинг тестов
2. **Playwright зависимости** - `test_nicegui_ui.py` требует установки playwright
3. **Устаревший AsyncClient API** - `test_user_crud_integration` использует старый API
4. **Пустые каталоги сервисов** - для DinD тестов нужно скопировать тестовые сервисы
5. **Фикстуры в conftest.py** - некоторые фикстуры дублируются между файлами

## API Endpoints

### Публичные (без аутентификации)
- `GET /healthz` — health check
- `GET /tls/validate?domain=...` — валидация домена для TLS

### Защищённые (требуют Bearer token)
- `GET/POST /api/users/` — управление пользователями
- `GET/PUT/DELETE /api/users/{id}` — операции с пользователем
- `GET /services/` — список сервисов
- `GET /services/{name}` — детали сервиса
- `POST /services/{name}/deploy` — деплой
- `POST /services/{name}/stop` — остановка
- `POST /services/{name}/restart` — перезапуск
- `GET /logs/service/{name}` — логи сервиса
- `GET /backups/service/{name}` — бэкапы сервиса
- `GET /deployments/service/{id}` — деплои сервиса

## CI/CD интеграция

```yaml
# .github/workflows/test.yml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # Level 0 & 1: Unit + Integration tests
      - name: Run pytest
        working-directory: _core/master
        run: |
          pip install poetry
          poetry install --with dev
          poetry run pytest tests/ -v --cov=app --cov-report=xml

      # Level 3: Full cycle (DinD)
      - name: Full cycle test
        working-directory: infra/test-env
        run: |
          docker compose up -d
          docker compose exec test-env ./test_full_cycle.sh
          docker compose down -v
```

## Добавление новых тестов

1. **Unit-тесты** → `tests/unit/test_<component>.py`
2. **Интеграционные тесты** → `tests/integration/test_<feature>.py`
3. **Тестовые данные** → `test-fixtures/`
4. **E2E тесты** → `infra/test-env/test-services/`

### Пример unit-теста для endpoint

```python
def test_get_service_success():
    """Тест успешного получения сервиса."""
    from app.main import app
    from app.core.security import get_current_user
    
    # Настраиваем моки
    app.state.discovery = mock_discovery
    app.state.docker = mock_docker
    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    
    try:
        client = TestClient(app)
        response = client.get("/services/test-service")
        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()
```

## [UPDATED] Troubleshooting

| Проблема | Решение |
|----------|---------|
| `ModuleNotFoundError: croniter` | `poetry install` или `pip install croniter` |
| `asyncio mode=STRICT` | Нужен `pytest-asyncio>=0.23` |
| DinD не стартует | Проверить `--privileged` флаг |
| Тесты падают на CI | Добавить `--no-cov` для ускорения |
| `404 Not Found` в тестах | Проверить что endpoint существует (см. API Endpoints) |
| Mock возвращает Mock | Добавить `.return_value = ...` |
| **`ModuleNotFoundError: playwright`** | **Установить: `pip install playwright` или пропустить тест: `-k "not nicegui"`** |
| **`sqlite3.OperationalError: unable to open database file`** | **Моки БД не работают. Проверить патчи `SessionLocal` в тестах BuiltInAuthProvider** |
| **`AsyncClient.__init__() got unexpected keyword argument 'app'`** | **Обновить тест: использовать `AsyncClient(app=app)` → `AsyncClient(app=app, base_url="http://test")`** |
| **Пустые каталоги `services/public/` и `services/internal/`** | **Скопировать тестовые сервисы: `cp -r infra/test-env/test-services/* services/`** |
