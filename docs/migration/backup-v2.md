# Миграция с Restic на Kopia (Backup v2)

## Обзор

Это руководство описывает процесс миграции с устаревшей системы резервного копирования (Restic + локальные бэкапы) на новую систему на основе **Kopia** с уведомлениями через **ntfy.sh/Apprise**.

### Что изменилось

| Компонент | Старая версия (v1) | Новая версия (v2) |
|-----------|---------------------|-------------------|
| **Движок бэкапов** | Restic (не реализован) + локальные rsync/pg_dump | Kopia с дедупликацией и шифрованием |
| **Хранилище** | Локальная директория `backups/` | Центральный Kopia репозиторий (файловая система, S3, SFTP) |
| **Уведомления** | Telegram | ntfy.sh / Apprise (поддерживает Telegram, Email, Slack и 50+ сервисов) |
| **Политики хранения** | Ручное удаление старых файлов | Автоматические политики Kopia (keep-daily, keep-weekly и т.д.) |
| **Управление** | Частичная реализация в UI | Полноценный UI с созданием, восстановлением, удалением |

### Ключевые преимущества Kopia

- **Дедупликация** — экономия места за счет хранения только уникальных блоков данных
- **Шифрование** — все данные шифруются на клиенте перед отправкой в хранилище
- **Множество бэкендов** — файловая система, S3, SFTP, Google Cloud Storage, Azure Blob
- **Гибкие политики** — автоматическое удаление старых снапшотов по настраиваемым правилам
- **Веб-интерфейс** — встроенный UI для просмотра и управления бэкапами

## Подготовка к миграции

### 1. Экспорт старых бэкапов (опционально)

Если у вас есть важные бэкапы в старой системе (директория `backups/`), рекомендуется экспортировать их перед миграцией:

```bash
# Создайте архив старых бэкапов
tar -czf old-backups-$(date +%Y%m%d).tar.gz backups/

# Скопируйте архив в безопасное место
scp old-backups-*.tar.gz backup-server:/storage/
```

### 2. Остановка старой системы бэкапов

Убедитесь, что старые cron-задачи и процессы бэкапов остановлены:

```bash
# Остановите контейнер backup (если существует)
docker stop _core-backup-1 2>/dev/null || true

# Удалите старые cron-задачи
docker exec _core-master-1 crontab -l | grep -v backup | crontab -
```

### 3. Резервное копирование конфигурации

Создайте резервную копию конфигурационных файлов:

```bash
cp -r _core/backup/ _core/backup.backup.$(date +%Y%m%d)/
cp _core/master/app/services/backup_manager.py _core/master/app/services/backup_manager.py.backup
```

## Процесс миграции

### Шаг 1: Обновление кода платформы

Убедитесь, что у вас установлена версия платформы с поддержкой Kopia (v2.0+). Если вы обновляете существующую установку:

```bash
# Получите последние изменения
git pull origin main

# Пересоберите контейнеры
docker compose -f _core/master/docker-compose.yml build
```

### Шаг 2: Настройка Kopia репозитория

#### Локальное хранилище (рекомендуется для начала)

1. Отредактируйте файл `_core/kopia/.env`:
   ```bash
   cp _core/kopia/.env.example _core/kopia/.env
   nano _core/kopia/.env
   ```

2. Установите следующие переменные:
   ```env
   # Обязательные
   KOPIA_REPOSITORY=/repository
   KOPIA_REPOSITORY_PASSWORD=secure_password_here  # Измените на свой пароль
   KOPIA_STORAGE_TYPE=filesystem
   
   # Опционально
   KOPIA_SERVER_USERNAME=admin
   KOPIA_SERVER_PASSWORD_FILE=/kopia/server.pass
   ```

3. Запустите сервис Kopia:
   ```bash
   docker compose -f _core/kopia/docker-compose.yml up -d
   ```

4. Инициализируйте репозиторий (если не создан автоматически):
   ```bash
   docker exec _core-kopia-1 kopia repository create filesystem \
     --path /repository \
     --password $KOPIA_REPOSITORY_PASSWORD
   ```

#### Удаленное хранилище (S3/SFTP)

Если вы хотите использовать удаленное хранилище, смотрите инструкции в `_core/kopia/.env.example`.

### Шаг 3: Настройка уведомлений (ntfy.sh/Apprise)

#### Вариант A: Публичный ntfy.sh (проще)

1. Выберите уникальный топик, например `platform-backups-ваш-проект`
2. Настройте переменные окружения в Master Service:
   ```env
   NTFY_TOPIC=platform-backups-ваш-проект
   NTFY_URL=https://ntfy.sh
   ```

#### Вариант B: Self-hosted ntfy

1. Разверните ntfy сервер (см. `_core/monitoring/ntfy/docker-compose.yml`)
2. Настройте переменные:
   ```env
   NTFY_TOPIC=backups
   NTFY_URL=https://ntfy.internal.example.com
   NTFY_USERNAME=admin
   NTFY_PASSWORD=secure_password
   ```

#### Вариант C: Apprise (множество сервисов)

Настройте `APPRISE_URLS` с нужными каналами:
```env
APPRISE_URLS="ntfy://backup-bot:password@ntfy.example.com/backups,mailto://user:pass@smtp.example.com/?to=admin@example.com,tgram://bottoken/ChatID"
```

### Шаг 4: Обновление конфигурации сервисов

Обновите раздел `backup` в `service.yml` каждого сервиса:

#### Старая конфигурация (v1):
```yaml
backup:
  enabled: true
  schedule: "0 2 * * *"
  retention: 7
  paths:
    - ./data
  databases:
    - type: postgres
      container: db
      database: myservice
```

#### Новая конфигурация (v2):
```yaml
backup:
  enabled: true
  schedule: "0 2 * * *"
  retention_days: 30
  paths:
    - ./data
  databases:
    - type: postgres
      container: db
      database: myservice
  kopia_policy:
    keep-daily: 7
    keep-weekly: 4
    keep-monthly: 6
    keep-annual: 2
  storage_type: filesystem  # или "s3", "sftp"
```

**Изменения:**
- `retention` → `retention_days` (используется для пометки в БД)
- Добавлен `kopia_policy` для управления хранением в Kopia
- Добавлен `storage_type` (должен соответствовать `KOPIA_STORAGE_TYPE`)

### Шаг 5: Перезапуск Master Service

После обновления конфигурации перезапустите Master Service:

```bash
docker compose -f _core/master/docker-compose.yml restart
```

### Шаг 6: Тестирование новой системы

1. **Создайте тестовый бэкап через UI:**
   - Перейдите на страницу "Backups"
   - Выберите сервис
   - Нажмите "Create Backup"
   - Убедитесь, что операция завершается успешно

2. **Проверьте наличие снапшота в Kopia:**
   ```bash
   docker exec _core-kopia-1 kopia snapshot list --manifest
   ```

3. **Проверьте уведомления:**
   - Подпишитесь на топик ntfy.sh или проверьте указанные каналы Apprise
   - Убедитесь, что пришло уведомление о успешном бэкапе

4. **Протестируйте восстановление:**
   - Выберите созданный бэкап в UI
   - Нажмите "Restore" (можно использовать тестовый сервис)
   - Убедитесь, что восстановление завершается успешно

## Пост-миграционные задачи

### 1. Очистка старых данных

После успешной миграции и проверки новой системы можно удалить старые данные:

```bash
# Удалите старую директорию бэкапов (если уверены)
rm -rf backups/

# Удалите старые контейнеры и образы
docker rm -f _core-backup-1 2>/dev/null || true
docker rmi backup-image 2>/dev/null || true
```

### 2. Обновление документации

Убедитесь, что вся документация ссылается на новую систему:
- Обновите `../user-guide/backup.md`
- Обновите `../user-guide/monitoring.md` (раздел уведомлений)
- Обновите `../TROUBLESHOOTING.md` (раздел бэкапов)

### 3. Мониторинг новой системы

Настройте мониторинг для Kopia репозитория:

```bash
# Регулярная проверка целостности (добавьте в cron)
0 3 * * * docker exec _core-kopia-1 kopia repository verify --password-file /kopia/password.txt

# Регулярное обслуживание (дедупликация, очистка)
0 4 * * 0 docker exec _core-kopia-1 kopia maintenance run
```

## Устранение проблем при миграции

### Проблема: Kopia репозиторий не инициализирован

**Решение:**
```bash
# Проверьте статус
docker exec _core-kopia-1 kopia repository status

# Если репозиторий не существует, создайте его
docker exec _core-kopia-1 kopia repository create filesystem \
  --path /repository \
  --password $KOPIA_REPOSITORY_PASSWORD
```

### Проблема: Уведомления не приходят

**Решение:**
1. Проверьте переменные окружения: `docker exec _core-master-1 env | grep NTFY`
2. Протестируйте отправку вручную: `curl -d "test" https://ntfy.sh/your-topic`
3. Проверьте логи: `docker logs _core-master-1 | grep -i apprise`

### Проблема: Бэкап не создается для сервиса

**Решение:**
1. Проверьте конфигурацию `service.yml` (правильные пути, контейнеры БД)
2. Проверьте логи Master Service: `docker logs _core-master-1 | grep -i backup`
3. Убедитесь, что Master Service имеет доступ к указанным путям

### Проблема: Ошибка "repository not found" или "invalid password"

**Решение:**
1. Убедитесь, что `KOPIA_REPOSITORY_PASSWORD` одинаков в Master Service и Kopia контейнере
2. Проверьте, что репозиторий существует: `docker exec _core-kopia-1 ls -la /repository`

## Откат к старой системе

Если возникли критические проблемы, можно временно откатиться:

1. **Восстановите старые конфигурации:**
   ```bash
   cp _core/backup.backup.*/_core/backup/
   cp _core/master/app/services/backup_manager.py.backup _core/master/app/services/backup_manager.py
   ```

2. **Перезапустите старый контейнер backup:**
   ```bash
   docker compose -f _core/backup/docker-compose.yml up -d
   ```

3. **Временно отключите Kopia в конфигурации сервисов:**
   ```yaml
   backup:
     enabled: false  # Отключите до решения проблем
   ```

## Часто задаваемые вопросы

### Q: Нужно ли мигрировать старые бэкапы в Kopia?
**A:** Нет, миграция старых бэкапов не предусмотрена. Kopia начинает работу с чистого состояния. Старые бэкапы можно хранить отдельно в архиве.

### Q: Можно ли использовать одновременно старую и новую систему?
**A:** Нет, системы несовместимы. После перехода на Kopia старая система бэкапов отключается.

### Q: Что происходит с данными в директории `backups/`?
**A:** Они остаются нетронутыми, но больше не используются. Вы можете удалить их после проверки работы новой системы.

### Q: Как изменить пароль Kopia репозитория после миграции?
**A:** Используйте команду `kopia repository change-password`. Подробнее в [документации Kopia](https://kopia.io/docs/reference/command-line/).

### Q: Поддерживает ли Kopia инкрементальные бэкапы?
**A:** Да, Kopia использует дедупликацию на уровне блоков, что эффективнее инкрементальных бэкапов.

## Дополнительные ресурсы

- [Документация Kopia](https://kopia.io/docs/)
- [Документация ntfy.sh](https://ntfy.sh/docs/)
- [Документация Apprise](https://github.com/caronc/apprise)
- [Руководство по бэкапам в платформе](../user-guide/backup.md)
- [Устранение неполадок с бэкапами](../TROUBLESHOOTING.md#проблемы-с-бэкапами-kopia)

## Поддержка

Если у вас возникли проблемы с миграцией, обратитесь:
1. К документации в `../`
2. К разделу устранения неполадок в `../TROUBLESHOOTING.md`
3. Создайте issue в репозитории проекта