# Restic upload в бэкапах

## Проблема

`_core/master/app/services/backup_manager.py`:

- `_upload_to_restic()` ссылается на `_core/backup/scripts/backup.sh` — директория `scripts/` удалена
- Исключение ловится и логируется — Restic-бэкапы тихо фейлятся
- rsync и pg_dump работают корректно

## Подход

1. Написать скрипт `backup.sh` для Restic (или использовать `subprocess` напрямую из Python)
2. Настроить `restic backup` с правильными переменными (`RESTIC_REPOSITORY`, `RESTIC_PASSWORD`)
3. Настроить ротацию через `restic forget --keep-daily 7 --prune`

## Папка

`./5-restic-upload/`
