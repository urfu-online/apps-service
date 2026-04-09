# Backup restore/delete в UI

## Проблема

`_core/master/app/ui/backups_page.py`:

- Кнопка restore — заглушка («Функция в разработке»)
- Кнопка delete — заглушка
- API-эндпоинты `POST /api/backups/.../restore` и `DELETE /api/backups/...` существуют

## Подход

1. Restore: вызвать API, показать прогресс, результат
2. Delete: вызвать API, подтверждение, обновление списка

## Папка

`./7-backup-restore-ui/`
