# LogManager — заглушка

## Проблема

`_core/master/app/services/log_manager.py`:

- In-memory `deque` — данные не персистентны
- `add_log_entry()` существует, но никто его не вызывает
- API-эндпоинты `/api/logs/service/{name}` обходят LogManager и читают напрямую из Docker API через `DockerManager.get_logs()`
- Комментарий в коде: «В реальной реализации здесь будет взаимодействие с Loki или Docker API»

## Подход

Два варианта:

1. **Простой (рекомендуется):** LogManager → wrapper вокруг `DockerManager.get_logs()`. Кеширование в памяти, TTL. Убрать заглушку, делегировать.
2. **Полный:** Интеграция с Docker API streaming logs → persistent storage (файлы или БД).

## Папка

`./4-log-manager/`
