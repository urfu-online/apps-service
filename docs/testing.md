# Тестирование платформы

Трёхуровневая система тестирования для безопасного обновления без риска для production.

## Уровни тестирования

### Level 1: Интеграционные тесты (быстро, ~10 сек)

Тестируют ключевые компоненты с моками: ServiceDiscovery, CaddyManager, DockerManager (dry-run).

```bash
# Локально (нужны зависимости poetry install)
cd _core/master
pytest tests/integration/test_full_deploy_cycle.py -v

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
- File watcher: `_is_service_config_file()` через `basename` (не `endswith`)

### Level 2: Dry-run режим (на хосте, ~30 сек)

Полный цикл без реального деплоя — только валидация команд.

```bash
# Через Python API
cd _core/master
python3 -c "
import asyncio
from app.services.docker_manager import DockerManager
from unittest.mock import AsyncMock

async def test():
    manager = DockerManager(AsyncMock())  # mock notifier
    manifest = ...  # ServiceManifest
    result = await manager.deploy_service(manifest, dry_run=True)
    print(result['logs'])  # Логирует команды без выполнения

asyncio.run(test())
"
```

**Что проверяет:**
- Подготовку docker compose команд
- Валидацию путей к файлам
- Логику формирования команд (build, pull, up)

### Level 3: DinD VM (полная симуляция сервера, ~5 мин)

Полноценная изолированная среда через Docker-in-Docker. Симулирует production сервер (`/apps`).

```bash
# Запуск DinD окружения
cd infra/test-env
docker compose up -d

# Вход в контейнер
docker compose exec test-env bash

# Запуск полного цикла тестов
./test_full_cycle.sh

# Очистка
docker compose down -v
```

**Что проверяет:**
- `install.sh` — генерация конфига
- `ServiceDiscovery` — реальное сканирование директорий
- `CaddyManager` — реальная генерация `.caddy` файлов
- `DockerManager` — реальный деплой через docker compose
- Health check — проверка HTTP эндпоинтов
- Полная очистка ресурсов

## Структура файлов

```
_core/master/
  tests/
    conftest.py                          # Фикстуры (mocks, fixtures)
    integration/
      test_full_deploy_cycle.py          # Level 1: интеграционные тесты
  test-fixtures/                         # Тестовые данные
    services/public/test-web-app/        #   сервисы с service.yml
    services/internal/test-api/
    caddy/templates/                     #   Caddy шаблоны
    caddy/snippets/
    caddy/conf.d/

infra/test-env/
  Dockerfile                             # DinD образ
  docker-compose.yml                     #   DinD compose
  test-services/                         #   тестовые сервисы для DinD
  test_full_cycle.sh                     #   скрипт полного цикла
```

## CI/CD интеграция

Для добавления в CI pipeline:

```yaml
# .github/workflows/test.yml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # Level 1: Integration tests
      - name: Run integration tests
        working-directory: _core/master
        run: docker compose -f docker-compose.yml -f docker-compose.test.yml up --build

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
3. **Тестовые данные** → `test-fixtures/` (не коммитить большие файлы)
4. **E2E тесты** → `infra/test-env/test-services/`

## Troubleshooting

| Проблема | Решение |
|----------|---------|
| `ModuleNotFoundError: croniter` | `pip install croniter` или `poetry install` |
| `asyncio mode=STRICT` | Нужен `pytest-asyncio>=0.23` |
| DinD не стартует | Проверить `--privileged` флаг |
| Тесты падают на CI | Добавить `--no-cov` для ускорения |
