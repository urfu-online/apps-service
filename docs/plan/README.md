# План работ

## Обзор

```
Уровень 1 (эта страница)    ← Что делаем и в каком порядке
Уровень 2 (task-файлы)      ← Детальное описание каждой задачи
Уровень 3 (task-папки)      ← Конкретика: код, логи, результаты, материалы
```

## Задачи (по приоритету)

### 1. Баги — крашат при использовании
**Где:** `_core/master/app/api/routes/deployments.py`, `_core/master/app/services/docker_manager.py`
**Что:** `AttributeError` при обращении к несуществующим методам/полям
**Статус:** Не начато
**Детали:** [1-deploy-bugs.md](1-deploy-bugs.md)

### 2. Мёртвые зависимости
**Где:** `_core/master/pyproject.toml`, `_core/master/app/`
**Что:** `aiodocker` — declared, never used; `python-multipart` — не используется
**Статус:** Не начато
**Детали:** [2-dead-deps.md](2-dead-deps.md)

### 3. Login endpoint в API
**Где:** `_core/master/app/api/routes/`
**Что:** Все эндпоинты за auth, но нет способа получить токен
**Статус:** Не начато
**Детали:** [3-login-endpoint.md](3-login-endpoint.md)

### 4. LogManager — заглушка
**Где:** `_core/master/app/services/log_manager.py`
**Что:** In-memory cache, данные не собираются, ничего не вызывает `add_log_entry`
**Статус:** Не начато
**Детали:** [4-log-manager.md](4-log-manager.md)

### 5. Бэкапы в Restic
**Где:** `_core/master/app/services/backup_manager.py`, `_core/backup/`
**Что:** rsync и pg_dump работают, upload в Restic — скрипты отсутствуют
**Статус:** Не начато
**Детали:** [5-restic-upload.md](5-restic-upload.md)

### 6. UI: детальная страница сервиса
**Где:** `_core/master/app/ui/services_page.py`
**Что:** `/services/{name}` — редирект на `/services`
**Статус:** Не начато
**Детали:** [6-service-detail-page.md](6-service-detail-page.md)

### 7. UI: backup restore/delete
**Где:** `_core/master/app/ui/backups_page.py`
**Что:** Кнопки — заглушки («Функция в разработке»)
**Статус:** Не начато
**Детали:** [7-backup-restore-ui.md](7-backup-restore-ui.md)

### 8. `_deploy_static` и `external` type
**Где:** `_core/master/app/services/docker_manager.py`
**Что:** Типы объявлены в enum, обработчики не написаны
**Статус:** Не начато
**Детали:** [8-static-external-types.md](8-static-external-types.md)

### 9. Миграции БД (Alembic)
**Где:** `_core/master/app/core/database.py`
**Что:** `create_all()` при старте, нет миграций
**Статус:** Не начато
**Детали:** [9-alembic-migrations.md](9-alembic-migrations.md)

### 10. Loki / Prometheus / Grafana
**Где:** `_core/` (директория `monitoring/` удалена)
**Что:** Документация ссылается, кода нет
**Статус:** Не начато — отдельная фича, не баг
**Детали:** [10-monitoring-stack.md](10-monitoring-stack.md)
