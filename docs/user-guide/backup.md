# Бэкапы и восстановление

> ⚠️ **Статус реализации**
>
> **✅ Работает:**
> - Бэкапы файлов и баз данных через Kopia с дедупликацией и шифрованием
> - Автоматическое создание бэкапов по расписанию (cron)
> - Ручное создание бэкапов через веб-интерфейс и API
> - Восстановление из бэкапов через веб-интерфейс и API
> - Уведомления о статусе через ntfy.sh/Apprise (Telegram, Email, Slack и др.)
> - Гибкие политики хранения (keep-daily, keep-weekly, keep-monthly)
> - Поддержка локального хранилища (filesystem) и S3/SFTP
>
> **❌ Не реализовано:**
> - Миграция старых бэкапов из Restic (чистый старт с Kopia)
> - Автоматическое восстановление при сбое сервиса
>
> **Примечание:** Все бэкапы хранятся в центральном Kopia-репозитории с шифрованием. Локальные копии в `backups/` больше не создаются.

## Общее описание

Система резервного копирования в платформе предоставляет автоматизированный и централизованный подход к созданию и управлению бэкапами сервисов с использованием **Kopia** — современного инструмента для резервного копирования с дедупликацией, шифрованием и поддержкой множества бэкендов. Основные возможности системы:

- Автоматическое создание бэкапов по расписанию (cron)
- Ручное создание бэкапов через веб-интерфейс и API
- Поддержка бэкапов файлов и баз данных (PostgreSQL, MySQL)
- Интеграция с Kopia для надежного хранения бэкапов
- Гибкое управление политиками хранения через Kopia policies
- Уведомления о статусе бэкапов через ntfy.sh/Apprise (поддерживаются Telegram, Email, Slack, Discord и др.)
- Поддержка локального хранилища (filesystem), S3, SFTP и других бэкендов Kopia

Система бэкапов работает на основе конфигурации, определенной в манифесте каждого сервиса (`service.yml`), что позволяет гибко настраивать бэкапы под конкретные требования каждого сервиса.

!!! warning "Deprecated"
    **Устаревшая информация:** В предыдущих версиях платформы использовались Restic для хранения бэкапов и Telegram для уведомлений. Начиная с версии 2.0, система перешла на Kopia и ntfy.sh/Apprise. Старые бэкапы в формате Restic не мигрируются автоматически — требуется ручной экспорт при необходимости.

## 2. Конфигурация бэкапов в манифесте service.yml

Конфигурация бэкапов определяется в файле `service.yml` каждого сервиса в разделе `backup`. Пример конфигурации:

```yaml
backup:
  enabled: true
  schedule: "0 2 * * *"        # Ежедневно в 02:00
  retention_days: 30            # Хранить бэкапы 30 дней (используется для пометки в БД)
  paths:
    - ./data
    - ./uploads
  databases:
    - type: postgres
      container: db
      database: myservice
  kopia_policy:
    keep-daily: 7
    keep-weekly: 4
    keep-monthly: 6
    keep-annual: 2
  storage_type: filesystem      # или "s3", "sftp"
  s3_endpoint: null             # требуется если storage_type=s3
  s3_bucket: null               # требуется если storage_type=s3
```

Параметры конфигурации:

- `enabled` - включение/выключение бэкапов для сервиса
- `schedule` - расписание бэкапов в формате cron (например, `"0 2 * * *"` для ежедневного бэкапа в 02:00)
- `retention_days` - количество дней хранения бэкапов (используется для пометки в БД, фактическое хранение управляется Kopia policy)
- `paths` - список путей к данным, которые нужно бэкапить (относительно корня сервиса)
- `databases` - список баз данных для бэкапа
- `kopia_policy` - политики хранения в Kopia (keep-daily, keep-weekly, keep-monthly, keep-annual)
- `storage_type` - тип хранилища: `filesystem` (локально), `s3`, `sftp` (должен соответствовать настройкам KOPIA_STORAGE_TYPE)
- `s3_endpoint`, `s3_bucket` - обязательны при `storage_type: s3`

## 3. Переменные окружения Kopia

Для работы системы бэкапов необходимо настроить следующие переменные окружения в Master Service:

```bash
# Обязательные переменные
KOPIA_REPOSITORY=/repository                    # Путь к репозиторию Kopia (или s3://...)
KOPIA_REPOSITORY_PASSWORD=secure_password_123   # Пароль для шифрования репозитория

# Опциональные переменные
KOPIA_STORAGE_TYPE=filesystem                   # filesystem, s3, sftp, gcs, azure
KOPIA_SERVER_USERNAME=admin                     # Имя пользователя для Kopia server
KOPIA_SERVER_PASSWORD_FILE=/kopia/server.pass   # Файл с паролем для Kopia server

# Для S3 хранилища
# KOPIA_STORAGE_TYPE=s3
# KOPIA_REPOSITORY=s3://bucket-name/path
# AWS_ACCESS_KEY_ID=your_access_key
# AWS_SECRET_ACCESS_KEY=your_secret_key
# AWS_REGION=us-east-1
# KOPIA_S3_ENDPOINT=https://s3.amazonaws.com

# Для SFTP хранилища
# KOPIA_STORAGE_TYPE=sftp
# KOPIA_REPOSITORY=sftp://user@host:port/path
# KOPIA_SFTP_PASSWORD=password
# KOPIA_SFTP_KEYFILE=/path/to/private_key
```

Эти переменные настраиваются в файле `_core/kopia/.env.example` и копируются в `.env` при развертывании.

## 4. Переменные окружения для уведомлений (ntfy.sh/Apprise)

Для отправки уведомлений о статусе бэкапов используются переменные:

```bash
# Использование ntfy.sh (публичный или self-hosted)
NTFY_TOPIC=backups                              # Топик для уведомлений
NTFY_URL=https://ntfy.sh                        # URL ntfy сервера

# Или использование Apprise с поддержкой множества сервисов
APPRISE_URLS="ntfy://backup-bot:password@ntfy.example.com/backups,mailto://user:pass@smtp.example.com/?to=admin@example.com"
```

Уведомления отправляются при следующих событиях:
- `backup.completed` - бэкап успешно создан
- `backup.failed` - ошибка при создании бэкапа
- `restore.completed` - восстановление успешно завершено
- `restore.failed` - ошибка при восстановлении

## 5. Планирование бэкапов (cron schedules)

Планирование бэкапов осуществляется с помощью стандартных cron-выражений. Платформа предоставляет несколько стандартных расписаний:

- Ежедневно: `0 2 * * *` (каждый день в 02:00)
- Еженедельно: `0 2 * * 0` (каждое воскресенье в 02:00)
- Ежемесячно: `0 2 1 * *` (первого числа каждого месяца в 02:00)
- Каждые 6 часов: `0 */6 * * *`

Вы можете использовать эти стандартные расписания или определить собственные в конфигурации сервиса.

## 6. Ручное создание бэкапов через веб-интерфейс

Для создания ручного бэкапа через веб-интерфейс:

1. Перейдите на страницу "Backups" в веб-интерфейсе
2. Выберите сервис из списка
3. Нажмите кнопку "Create Backup"
4. Дождитесь завершения операции (прогресс отображается в реальном времени)

Статус создания бэкапа будет отображаться в уведомлениях интерфейса и отправлен через настроенный канал уведомлений (ntfy/Apprise).

## 7. Ручное создание бэкапов через API

Для создания ручного бэкапа через API, отправьте POST-запрос:

```bash
curl -X POST "https://platform.example.com/api/backups/service/{service_name}/backup" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "manual"}'
```

Ответ содержит идентификатор созданного снапшота Kopia:
```json
{
  "snapshot_id": "k1234567890abcdef",
  "service_name": "my-service",
  "status": "completed",
  "created_at": "2026-04-23T22:10:00Z",
  "size_bytes": 10485760
}
```

## 8. Просмотр списка бэкапов

### Через веб-интерфейс

1. Перейдите на страницу "Backups"
2. Выберите сервис из списка
3. Нажмите "Show Backups" для отображения списка бэкапов

Таблица отображает:
- ID снапшота Kopia
- Дата создания
- Статус (🟢 Успешно, 🟡 В процессе, 🔴 Ошибка)
- Размер
- Действия (Restore, Delete)

### Через API

```bash
curl -X GET "https://platform.example.com/api/backups/service/{service_name}" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 9. Восстановление из бэкапа через веб-интерфейс

Для восстановления из бэкапа через веб-интерфейс:

1. Перейдите на страницу "Backups"
2. Выберите сервис и отобразите список бэкапов
3. Нажмите кнопку "Restore" напротив нужного бэкапа
4. Подтвердите операцию восстановления
5. Дождитесь завершения (прогресс отображается в реальном времени)

Внимание: восстановление из бэкапа может повлиять на текущие данные сервиса. Рекомендуется останавливать сервис перед восстановлением.

## 10. Восстановление из бэкапа через API

Для восстановления из бэкапа через API:

```bash
curl -X POST "https://platform.example.com/api/backups/service/{service_name}/restore" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"snapshot_id": "k1234567890abcdef"}'
```

## 11. Управление политиками хранения бэкапов

Политики хранения бэкапов определяются двумя способами:

1. **Пометка в БД**: параметр `retention_days` в конфигурации сервиса определяет, сколько дней бэкап считается актуальным в интерфейсе платформы.

2. **Фактическое хранение в Kopia**: управляется через `kopia_policy` в конфигурации сервиса. Kopia автоматически удаляет старые снапшоты согласно политике:
   - `keep-daily`: N - хранить последние N дневных снапшотов
   - `keep-weekly`: N - хранить последние N недельных снапшотов  
   - `keep-monthly`: N - хранить последние N месячных снапшотов
   - `keep-annual`: N - хранить последние N годовых снапшотов

Для изменения политики хранения:
1. Отредактируйте параметры `retention_days` и `kopia_policy` в `service.yml`
2. Перезапустите сервис для применения изменений
3. Kopia автоматически применит новую политику при следующем обслуживании

## 12. Бэкапы баз данных (PostgreSQL, MySQL)

Система поддерживает бэкапы следующих типов баз данных:

### PostgreSQL

```yaml
databases:
  - type: postgres
    container: db          # Имя контейнера с PostgreSQL
    database: myservice    # Имя базы данных
    # Опционально: username, password, host, port
```

### MySQL

```yaml
databases:
  - type: mysql
    container: db          # Имя контейнера с MySQL
    database: myservice    # Имя базы данных
    # Опционально: username, password, host, port
```

Бэкапы баз данных создаются с помощью соответствующих утилит (`pg_dump` для PostgreSQL и `mysqldump` для MySQL) внутри контейнеров сервисов. Дампы сохраняются во временную staging-директорию, а затем загружаются в Kopia репозиторий.

## 13. Уведомления о бэкапах через ntfy.sh/Apprise

Платформа отправляет уведомления о статусе бэкапов через ntfy.sh или Apprise (поддерживает 50+ сервисов):

- Успешное завершение бэкапа
- Ошибки при создании бэкапа
- Завершение восстановления
- Предупреждения о истечении срока хранения

### Настройка ntfy.sh

1. **Публичный ntfy.sh**: просто укажите топик
   ```bash
   NTFY_TOPIC=backups
   NTFY_URL=https://ntfy.sh
   ```

2. **Self-hosted ntfy**: укажите URL вашего сервера
   ```bash
   NTFY_TOPIC=backups
   NTFY_URL=https://ntfy.internal.example.com
   ```

### Настройка Apprise

Apprise поддерживает множество сервисов через единый URL-формат:

```bash
APPRISE_URLS="ntfy://backup-bot:password@ntfy.example.com/backups,mailto://user:pass@smtp.example.com/?to=admin@example.com,tgram://bottoken/ChatID,slack://token-a/token-b/token-c/#channel"
```

Примеры URL:
- Telegram: `tgram://{bot_token}/{chat_id}`
- Email: `mailto://{user}:{pass}@{smtp_host}/{to_email}`
- Slack: `slack://{token_a}/{token_b}/{token_c}/#{channel}`
- Discord: `discord://{webhook_id}/{webhook_token}`

## 14. Устранение неполадок бэкапов

### Распространенные проблемы

1. **Бэкап не создается**
   - Проверьте, включены ли бэкапы в конфигурации сервиса (`backup.enabled: true`)
   - Проверьте логи Master Service на наличие ошибок: `docker logs master`
   - Убедитесь, что переменные окружения KOPIA_REPOSITORY и KOPIA_REPOSITORY_PASSWORD установлены
   - Проверьте доступ к данным для бэкапа (права на чтение путей)

2. **Ошибка при бэкапе базы данных**
   - Проверьте, запущен ли контейнер с базой данных
   - Убедитесь, что указаны правильные параметры подключения (container, database)
   - Проверьте логи контейнера базы данных
   - Убедитесь, что у пользователя базы данных есть права на чтение

3. **Проблемы с Kopia репозиторием**
   - Проверьте статус репозитория: `kopia repository status --password-file <(echo $KOPIA_REPOSITORY_PASSWORD)`
   - Просмотрите список снапшотов: `kopia snapshot list --manifest`
   - Проверьте доступность хранилища (диск, S3, SFTP)
   - Убедитесь, что пароль репозитория указан правильно

4. **Уведомления не приходят**
   - Проверьте настройки NTFY_TOPIC или APPRISE_URLS
   - Протестируйте отправку вручную: `curl -d "test" https://ntfy.sh/your-topic`
   - Проверьте логи AppriseNotifier в Master Service
   - Убедитесь, что сетевой доступ к сервису уведомлений есть

### Проверка логов

Для диагностики проблем с бэкапами проверьте логи:

- Логи Master Service: `docker logs master`
- Логи Kopia: `docker logs kopia`
- Логи скриптов бэкапа: `tail -f /var/log/kopia_backup.log`
- Логи контейнеров сервисов

### Ручной запуск бэкапа

Для тестирования можно запустить бэкап вручную через CLI:

```bash
# Внутри контейнера master
python -m app.services.kopia_backup_manager run_backup --service test-svc --dry-run

# Или через platform CLI
platform backup create test-svc --dry-run
```

### Команды Kopia для диагностики

```bash
# Просмотр всех снапшотов
kopia snapshot list --manifest

# Статус репозитория
kopia repository status

# Просмотр содержимого снапшота
kopia snapshot list k1234567890abcdef --details

# Запуск обслуживания репозитория
kopia maintenance run