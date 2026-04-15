# Процесс выпуска релиза

Этот документ описывает стандартный процесс подготовки, тестирования и фиксации релиза для платформы apps-service-opus. Следуйте этим шагам, чтобы обеспечить стабильность и предсказуемость выпуска.

## 1. Подготовка к релизу

Перед созданием релизной ветки убедитесь, что код находится в стабильном состоянии.

### 1.1 Проверка зависимостей

Убедитесь, что `poetry.lock` синхронизирован с `pyproject.toml` и не содержит конфликтов.

```bash
cd _core/master
poetry lock --no-update
git diff poetry.lock
```

Если есть изменения, обновите lock-файл:

```bash
poetry update
git add poetry.lock
git commit -m "chore: update dependencies"
```

**Чеклист:**
- [ ] `poetry.lock` актуален (нет изменений после `poetry lock --no-update`)
- [ ] Все зависимости имеют явные версии
- [ ] Нет уязвимостей (`poetry check`)

### 1.2 Запуск тестов

Выполните все уровни тестирования, описанные в [testing.md](testing.md).

**Level 1: Интеграционные тесты (быстро)**
```bash
cd _core/master
make test
```

**Level 2: Dry-run режим**
```bash
cd _core/master
python3 -c "
import asyncio
from app.services.docker_manager import DockerManager
from unittest.mock import AsyncMock

async def test():
    manager = DockerManager(AsyncMock())
    manifest = ...  # ServiceManifest
    result = await manager.deploy_service(manifest, dry_run=True)
    print(result['logs'])

asyncio.run(test())
"
```

**Level 3: DinD VM (полная симуляция)**
```bash
cd infra/test-env
docker compose up -d
docker compose exec test-env bash
./test_full_cycle.sh
docker compose down -v
```

**Чеклист:**
- [ ] Все unit-тесты проходят (`make test`)
- [ ] Интеграционные тесты проходят (`pytest tests/integration/`)
- [ ] DinD окружение успешно проходит полный цикл
- [ ] Покрытие кода не ухудшилось (`make test-cov`)

### 1.3 Проверка документации

Обновите документацию, если были добавлены новые функции или изменены API.

```bash
# Проверить, что все .md файлы корректно отображаются
cd docs
mkdocs serve  # локальная проверка
```

**Чеклист:**
- [ ] README.md актуален
- [ ] CHANGELOG.md обновлён (см. раздел 4)
- [ ] API документация соответствует текущему состоянию
- [ ] Нет битых ссылок (`mkdocs build --strict`)

### 1.4 Проверка стиля кода

Убедитесь, что код соответствует стандартам Ruff.

```bash
cd _core/master
poetry run ruff check . --fix
poetry run ruff format .
```

**Чеклист:**
- [ ] Ruff проверка не выявляет ошибок (категории E, F, W, I, N, UP, B, C4)
- [ ] Длина строк не превышает 120 символов
- [ ] Форматирование соответствует black/isort

## 2. Тестирование релиза

Перед фиксацией релиза необходимо провести тестирование в максимально приближенной к production среде.

### 2.1 DinD окружение

Запустите полный цикл тестирования в DinD, который симулирует серверную среду.

```bash
cd infra/test-env
docker compose up -d --build
docker compose exec test-env bash

# Внутри контейнера:
cd /apps
./test_full_cycle.sh
```

**Что проверяется:**
- Service discovery сканирует `services/{public,internal}/`
- Caddy генерирует корректные конфиги из шаблонов
- DockerManager может развернуть тестовые сервисы
- Health checks работают (каждые 30 секунд)
- Локальные переопределения (`service.local.yml`) обрабатываются правильно

### 2.2 Интеграционные тесты с реальным Docker

Если на локальной машине есть Docker, запустите тесты с реальным Docker (не dry-run).

```bash
cd _core/master
docker compose -f docker-compose.yml -f docker-compose.test.yml up --build --abort-on-container-exit
```

### 2.3 Проверка миграций БД

Убедитесь, что изменения в моделях не ломают существующую базу данных.

```bash
cd _core/master
# Создать тестовую БД
rm -f test.db
python3 -c "
from app.core.database import engine, Base
Base.metadata.create_all(bind=engine)
print('Database schema created successfully')
"
```

**Чеклист:**
- [ ] DinD тесты проходят без ошибок
- [ ] Все сервисы из `test-fixtures/` успешно деплоятся
- [ ] Caddy конфиги генерируются корректно
- [ ] Health checks возвращают 200 OK
- [ ] Нет утечек ресурсов (контейнеры останавливаются)

## 3. Создание релизной ветки и тега

После успешного тестирования создайте релизную ветку и тег.

### 3.1 Подготовка ветки

```bash
# Перейти на main и обновить
git checkout main
git pull origin main

# Создать релизную ветку
git checkout -b release/v1.2.0

# Обновить версию в pyproject.toml (если нужно)
poetry version patch  # или minor, major
```

### 3.2 Создание тега

Перед созданием тега убедитесь, что все коммиты готовы.

```bash
# Просмотреть историю
git log --oneline -10

# Создать аннотированный тег
git tag -a v1.2.0 -m "Release v1.2.0

- Добавлена поддержка X
- Исправлена ошибка Y
- Обновлены зависимости"

# Отправить тег в удалённый репозиторий
git push origin v1.2.0
```

### 3.3 Git workflow для релизов

Рекомендуемый workflow:
1. `main` — стабильная ветка, всегда готовая к релизу
2. `release/*` — ветка для подготовки конкретного релиза (опционально)
3. Теги создаются от коммита в `main` после мержа релизной ветки

```bash
# После тестирования в release/v1.2.0
git checkout main
git merge --no-ff release/v1.2.0 -m "Merge release v1.2.0"
git tag v1.2.0
git push origin main v1.2.0
```

## 4. Обновление документации

### 4.1 CHANGELOG

Ведение CHANGELOG обязательно. Формат — [Keep a Changelog](https://keepachangelog.com/).

```bash
# Создать или обновить CHANGELOG.md
cat >> CHANGELOG.md << 'EOF'

## [1.2.0] - $(date +%Y-%m-%d)

### Added
- Новая функциональность X

### Changed
- Обновлены зависимости

### Fixed
- Исправлена ошибка Y
EOF
```

### 4.2 Версионирование

Используйте семантическое версионирование (SemVer):
- **MAJOR** — обратно несовместимые изменения
- **MINOR** — новая функциональность с обратной совместимостью
- **PATCH** — исправления ошибок с обратной совместимостью

Версия хранится в:
- `_core/master/pyproject.toml` (для master service)
- `_core/platform-cli/pyproject.toml` (для platform-cli)
- Git теги

### 4.3 Обновление документации MkDocs

Если были изменения в документации, обновите сайт.

```bash
cd docs
mkdocs build
# Проверить сгенерированный сайт
```

## 5. Проверка работоспособности

Перед окончательным выпуском выполните финальные проверки.

### 5.1 Финальный чеклист

- [ ] Все тесты проходят на CI (если есть)
- [ ] DinD окружение успешно завершило полный цикл
- [ ] Синхронизация poetry.lock проверена
- [ ] CHANGELOG обновлён
- [ ] Версия в pyproject.toml соответствует тегу
- [ ] Документация актуальна
- [ ] Код соответствует стилю (ruff)
- [ ] Миграции БД протестированы
- [ ] Caddy шаблоны не сломаны

### 5.2 Проверка на сервере (опционально)

Если есть staging-сервер, разверните там релиз для финальной проверки.

```bash
ssh staging-server "cd /apps && git fetch --tags && git checkout v1.2.0"
ssh staging-server "cd /apps && ./restart_core.sh --build"
```

## 6. Выпуск релиза

### 6.1 Создание релиза на GitHub

Если используется GitHub, создайте релиз через интерфейс или CLI:

```bash
# Используя gh CLI
gh release create v1.2.0 --title "v1.2.0" --notes-file CHANGELOG.md
```

### 6.2 Публикация (если нужно)

Для этого проекта публикация в PyPI не требуется, так как это внутренний сервис. Однако platform-cli может быть опубликован как pip-пакет.

```bash
cd _core/platform-cli
poetry build
poetry publish  # если настроен репозиторий
```

### 6.3 Уведомление команды

После успешного выпуска:
- Обновите статус в трекере задач
- Уведомите команду о выпуске
- Запланируйте деплой на production (если не автоматический)

## 7. Пострелизные действия

### 7.1 Обновление окружения разработки

Убедитесь, что разработчики могут переключиться на новый релиз.

```bash
git pull origin main
poetry install
```

### 7.2 Мониторинг

После деплоя на production отслеживайте:
- Логи master сервиса
- Health checks сервисов
- Ошибки Caddy

### 7.3 Обратная связь

Соберите обратную связь о релизе и используйте её для улучшения процесса.

## Приложение A: Быстрый чеклист релиза

```bash
# 1. Подготовка
cd _core/master
poetry lock --no-update
make test

# 2. Тестирование
cd ../../infra/test-env
docker compose up -d
docker compose exec test-env bash -c "cd /apps && ./test_full_cycle.sh"
docker compose down -v

# 3. Создание тега
git checkout main
git pull origin main
poetry version patch
git add pyproject.toml
git commit -m "Bump version to $(poetry version -s)"
git tag v$(poetry version -s)
git push origin main --tags

# 4. Документация
update CHANGELOG.md
mkdocs build --strict

# 5. Выпуск
gh release create v$(poetry version -s) --generate-notes
```

## Приложение B: Частые проблемы

### Рассинхрон poetry.lock
**Симптомы:** Ошибки импорта после обновления.
**Решение:** `docker compose build --no-cache` и `poetry lock`.

### Caddy не генерирует конфиги
**Решение:** Перезапустить Caddy через API: `curl -X POST http://localhost:8001/api/caddy/reload`

### Health checks не работают
**Проверка:** У всех сервисов должен быть `health_check.endpoint` в `service.yml`.

### DinD тесты падают
**Проверка:** Убедитесь, что Docker-in-Docker правильно настроен и есть доступ к сокету.

---

*Последнее обновление: $(date +%Y-%m-%d)*
*Авторы: команда разработки apps-service-opus*