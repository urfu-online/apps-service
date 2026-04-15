# Шпаргалка: обновление платформы на сервере

## 1. Узнать что сейчас на сервере

```bash
ssh <сервер> "cd /apps && git log --oneline -5"
ssh <сервер> "cd /apps && git status"
ssh <сервер> "cd /apps && git branch -a"
```

Первая команда покажет последний коммит, вторая — есть ли локальные изменения, третья — текущую ветку и удалённые ветки. Убедись, что находишься на ветке `main` (или `master`), а не на `platform-cli` или другой feature-ветке.

## 2. Что тестировать где

| Что проверяешь | Где |
|---|---|
| Код работает, тесты проходят | **Локально** — DinD (`infra/test-env/`) |
| Миграции БД, существующие сервисы | **Сервер** — только тут реальные данные |
| Caddy + SSL + DNS | **Сервер** — на локале нет доменов |
| Конфликты с ручными правками админа | **Сервер** — только тут они есть |
| Синхронизация poetry.lock | **Локально и на сервере** — через `docker compose build` |

**DinD не заменит сервер** — там нет реальных сервисов, данных, ручных правок конфига. DinD — только "код вообще запускается".

## 3. Процесс обновления (безопасный)

### Шаг 1: Подготовка (локально)

```bash
# Убедиться что main свежий
git pull origin main

# Посмотреть что изменилось
git log --oneline origin/main..HEAD  # если есть локальные коммиты
git diff HEAD~3 --stat               # что поменялось за последние коммиты
```

### Шаг 2: Бэкап (на сервере) — ОБЯЗАТЕЛЬНО

```bash
ssh <сервер>

# Остановить master (чтобы не писал в БД во время бэкапа)
cd /apps
sudo docker compose -f _core/master/docker-compose.yml down

# Забэкапить БД
sudo cp _core/master/master.db /tmp/master.db.backup.$(date +%Y%m%d)

# Забэкапить все service.yml сервисов
sudo tar czf /tmp/services-backup.$(date +%Y%m%d).tgz services/

# Забэкапить текущий конфиг Caddy
sudo tar czf /tmp/caddy-backup.$(date +%Y%m%d).tgz _core/caddy/

# Проверить что бэкапы создались
ls -lh /tmp/*.backup.* /tmp/*.tgz
```

**Примечание:** Используем `sudo` для доступа к файлам, которые могут принадлежать root (например, если контейнеры запускались от root). Если Docker запущен от текущего пользователя, sudo можно опустить.

### Шаг 3: Проверка синхронизации poetry.lock и pyproject.toml

Если в изменениях есть обновления зависимостей в `pyproject.toml`, нужно убедиться, что `poetry.lock` актуален. На сервере это делается через пересборку образа:

```bash
cd /apps/_core/master
sudo docker compose build --no-cache  # или --build при запуске
```

Можно также проверить локально, что lock-файл сгенерирован:

```bash
poetry lock --no-update
git diff poetry.lock
```

### Шаг 4: Работа с ветками (если нужно)

Иногда на сервере остаётся ветка `platform-cli` (из тестирования CLI). Перед обновлением переключись на `main`:

```bash
cd /apps
git checkout main
git branch -a  # проверить
```

Если есть незакоммиченные изменения, можно сохранить их в stash:

```bash
git stash
git stash list
```

После обновления можно вернуть изменения (если они нужны) или удалить stash.

### Шаг 5: Pull на сервере

```bash
cd /apps

# Проверить нет ли локальных изменений
git status
git stash  # если есть — сохранить

# Обновить код
git pull origin main

# Посмотреть что обновилось
git log --oneline -5
```

### Шаг 6: Перезапуск core

```bash
cd /apps

# Пересобрать и перезапустить master + caddy
./restart_core.sh --build

# Проверить что запустились
sudo docker ps | grep -E "master|caddy"
sudo docker logs platform-master --tail 20
```

### Шаг 7: Проверка после обновления

```bash
# Master UI
curl -s http://localhost:8001/healthz

# Caddy
curl -s http://localhost:80/ -o /dev/null -w "%{http_code}"

# Логи master
sudo docker logs platform-master --tail 50

# Проверить что сервисы на месте
cd /apps && ops list   # или platform list

# Проверить сеть Docker
sudo docker network ls | grep platform_network

# Проверить состояние всех контейнеров
sudo docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

### Шаг 8: Проверка сервисов

```bash
# Пройтись по ключевым сервисам
curl http://<домен-сервиса>/healthz
# или
sudo docker ps --format "table {{.Names}}\t{{.Status}}"
```

### Если что-то пошло не так — откат

```bash
cd /apps

# Откатить git
git reset --hard HEAD~1  # или к нужному коммиту

# Восстановить БД
sudo cp /tmp/master.db.backup.YYYYMMDD _core/master/master.db

# Перезапустить
./restart_core.sh
```

## 4. Что может сломаться

| Риск | Почему | Как проверить |
|---|---|---|
| Миграции БД | Нет Alembic, `create_all()` | master.log при старте |
| Caddy конфиг | Генерируется заново, могли быть ручные правки | Сравнить `_core/caddy/conf.d/` до/после |
| Docker network | `platform_network` может не существовать после ребута | `docker network ls` |
| Зависимости | Новый pyproject.toml, старые образы | `restart_core.sh --build` пересоберёт |
| Local override | `.ops-config.local.yml` — gitignored, не затронется | `git status` покажет если есть |
| Poetry.lock рассинхрон | lock-файл не обновлён после изменений pyproject.toml | `docker compose build` с ошибкой |

## 5. Частые проблемы и решения

### Проблема 1: После pull не обновляется poetry.lock
**Симптомы:** Контейнер master не запускается, ошибки импорта модулей.
**Решение:** Принудительно пересобрать образ с `--build`:
```bash
cd /apps/_core/master
sudo docker compose build --no-cache
cd /apps
./restart_core.sh --build
```

### Проблема 2: Caddy не генерирует конфиги для новых сервисов
**Симптомы:** Сервис добавлен, но недоступен по домену.
**Решение:** Перезапустить Caddy через API master или пересоздать конфиги:
```bash
curl -X POST http://localhost:8001/api/caddy/reload
```
Если не помогает, проверить логи Caddy:
```bash
sudo docker logs platform-caddy
```

### Проблема 3: Ветка platform-cli осталась активной
**Симптомы:** Команды `ops` не работают, потому что код CLI устарел.
**Решение:** Переключиться на main и перезапустить core:
```bash
cd /apps
git checkout main
./restart_core.sh --build
```

### Проблема 4: Бэкап не удался из-за прав
**Симптомы:** Ошибка "Permission denied" при копировании БД.
**Решение:** Использовать sudo для копирования и архивации, либо изменить владельца файлов:
```bash
sudo chown -R $USER:$USER _core/master/master.db
```

### Проблема 5: После обновления не работают health checks
**Симптомы:** В UI сервисы показываются как "unhealthy", хотя они работают.
**Решение:** Проверить endpoint health check в service.yml, убедиться что он возвращает 200. Перезапустить health checker:
```bash
sudo docker restart platform-master
```

### Проблема 6: Docker network отсутствует
**Симптомы:** Сервисы не могут соединиться друг с другом.
**Решение:** Создать сеть вручную:
```bash
sudo docker network create platform_network
```
Или перезапустить все контейнеры заново.

## 6. Чеклист перед обновлением

- [ ] Бэкап БД сделан (с sudo)
- [ ] Бэкап сервисов сделан (с sudo)
- [ ] Бэкап Caddy конфига сделан (с sudo)
- [ ] Список сервисов записан (`ops list > /tmp/services-before.txt`)
- [ ] Проверена текущая ветка (`git branch`)
- [ ] Проверена синхронизация poetry.lock
- [ ] Есть план отката (бэкапы на месте)
- [ ] Есть время на фикс если что-то пойдёт не так
- [ ] Telegram уведомления работают (узнаешь если мастер упадёт)

## 7. Быстрые команды для копирования

```bash
# Полный процесс одной строкой (после ssh)
cd /apps && sudo docker compose -f _core/master/docker-compose.yml down && \
sudo cp _core/master/master.db /tmp/master.db.backup.$(date +%Y%m%d) && \
sudo tar czf /tmp/services-backup.$(date +%Y%m%d).tgz services/ && \
sudo tar czf /tmp/caddy-backup.$(date +%Y%m%d).tgz _core/caddy/ && \
git stash && git pull origin main && ./restart_core.sh --build
```

**Примечание:** Используйте с осторожностью, лучше выполнять по шагам.

---
*Последнее обновление: 2026-04-15 (на основе опыта обновления платформы)*