# `_deploy_static` и `external` service type

## Проблема

`_core/master/app/services/docker_manager.py:deploy_service()`:

```python
if service.type == "docker-compose":
    ...
elif service.type == "docker":
    result = await self._deploy_single(...)  # существует?
elif service.type == "static":
    result = await self._deploy_static(...)  # НЕ СУЩЕСТВУЕТ → NameError
# external — нет обработчика, falls through
```

## Подход

- `static` — сервис без контейнеров (просто файлы, Nginx отдаёт). Можно отложить
- `external` — сервис вне платформы (только роутинг через Caddy). Можно отложить

Рекомендация: убрать из `deploy_service()` или добавить stub с предупреждением.

## Папка

`./8-static-external-types/`
