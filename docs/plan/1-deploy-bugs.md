# Баги в deployments.py и docker_manager.py

## Проблема

Три бага, каждый вызывает `AttributeError` при использовании.

### 1. `get_service_by_id` не существует

**Файл:** `_core/master/app/api/routes/deployments.py:258`

```python
service_manifest = app.state.discovery.get_service_by_id(deployment.service_id)
```

`ServiceDiscovery` имеет только `get_service(name: str)`, не `get_service_by_id`.

### 2. `ServiceManifest` не имеет поля `id`

**Файл:** `_core/master/app/api/routes/deployments.py:114`

```python
for service in app.state.discovery.services.values():
    if service.id == service_id:  # AttributeError
```

`ServiceManifest` — Pydantic-модель, у неё нет `id`. Есть `name`.

### 3. Pull/build результаты не проверяются

**Файл:** `_core/master/app/services/docker_manager.py:89-96`

```python
if pull:
    pull_result = await self._run_command(cmd + ["pull"])  # result не используется
if build:
    build_result = await self._run_command(cmd + ["build", "--no-cache"])  # result не используется

# Только up_result определяет успех
return {"success": up_result["returncode"] == 0, ...}
```

Если pull/build упал, но `up` succeeded с old image — деплой считается успешным.

## Подход к исправлению

1. Заменить `get_service_by_id` на поиск по `name` (deployment должен хранить имя сервиса, не ID)
2. Заменить `service.id` на `service.name` в deployments.py
3. Добавить проверку returncode для pull/build команд — возвращать failure если они упали

## Папка

Материалы по задаче — `./1-deploy-bugs/`
