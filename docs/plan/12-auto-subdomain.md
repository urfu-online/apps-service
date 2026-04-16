# Автоматизация маршрутизации и SSL для поддоменов 4-го уровня

**Issue:** [#37](https://github.com/urfu-online/apps-service/issues/37)

## Цель

Встроить механизм автоматического назначения доменов `{service}.apps.urfu.online` с zero-touch SSL через Caddy `on_demand_tls`.

## Архитектура

### Компоненты

| Компонент | Изменения |
|-----------|-----------|
| `service.yml` | Флаг `routing.auto_subdomain: true` |
| `discovery.py` | RoutingConfigModel + `auto_subdomain`, `base_domain` |
| `caddy_manager.py` | Генерация `{name}.apps.urfu.online` конфигов |
| `Caddyfile` | `on_demand_tls { ask }` блок |
| API | `GET /api/tls/validate?domain=` |

### Поток

```
1. Деплой сервиса с auto_subdomain: true
2. caddy_manager генерирует {name}.apps.urfu.online.caddy
3. Caddy загружает конфиг через Admin API
4. Первый HTTPS-запрос → ACME challenge
5. Caddy вызывает /api/tls/validate?domain=...
6. Master проверяет: домен зарегистрирован? → 200/403
7. Если 200 → Caddy выпускает сертификат
```

## Реализация

### 1. Модель (discovery.py)

```python
class RoutingConfigModel(BaseModel):
    type: str  # domain, subfolder, port
    # ... существующие поля ...
    auto_subdomain: bool = False  # NEW
    base_domain: str = "apps.urfu.online"  # NEW
```

### 2. Эндпоинт валидации (api/tls.py)

```python
@router.get("/api/tls/validate")
async def validate_tls_domain(domain: str, discovery: ServiceDiscovery):
    """
    Валидация домена для on_demand_tls.
    Возвращает 200 если домен разрешён, 403 если нет.
    """
    # Проверка формата
    if not domain.endswith(".apps.urfu.online"):
        raise HTTPException(403, "Domain not in allowed zone")
    
    # Извлечение имени сервиса
    service_name = domain.rsplit(".apps.urfu.online", 1)[0]
    
    # Проверка регистрации
    if service_name not in discovery.services:
        raise HTTPException(403, "Service not registered")
    
    return {"status": "ok", "service": service_name}
```

### 3. Caddyfile

```caddy
{
    email admin@urfu.online
    admin 0.0.0.0:2019
    
    on_demand_tls {
        ask http://master:8000/api/tls/validate
    }
}

# ... остальное ...

# Wildcard для автоматических поддоменов
*.apps.urfu.online {
    tls { on_demand }
    
    log {
        output file /var/log/caddy/acme.log {
            roll_size 50mb
            roll_keep 5
        }
    }
    
    # Маршрутизация через импорт конфигов сервисов
    import /etc/caddy/conf.d/*.caddy
}
```

### 4. Шаблон конфига (auto_subdomain.caddy.j2)

```caddy
# Auto-subdomain: {{ service.name }}
{{ service.name }}.{{ base_domain }} {
    import common_headers
    import logging {{ service.name }} auto_subdomain
    
    {% if route.container_name %}
    reverse_proxy http://{{ route.container_name }}:{{ route.internal_port }} {
    {% else %}
    reverse_proxy host.docker.internal:{{ route.internal_port }} {
    {% endif %}
        {% if service.health.enabled %}
        health_uri {{ service.health.endpoint }}
        health_interval {{ service.health.interval }}
        {% endif %}
        
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
        header_up X-Service-Name {{ service.name }}
    }
}
```

## Пример service.yml

```yaml
name: test-svc
type: docker
visibility: public

routing:
  - auto_subdomain: true
    base_domain: apps.urfu.online
    internal_port: 8000
    container_name: test-svc

health:
  enabled: true
  endpoint: /health
```

## Критерии приёмки

- [ ] `auto_subdomain: true` генерирует `{name}.apps.urfu.online`
- [ ] `/api/tls/validate` возвращает 200 для зарегистрированных, 403 для остальных
- [ ] Caddy выпускает сертификат при первом HTTPS-запросе
- [ ] Незарегистрированные поддомены не триггерят ACME
- [ ] Логи ACME пишутся в `/var/log/caddy/acme.log`

## Риски

| Риск | Митигация |
|------|-----------|
| Rate limits LE | Кэш списка доменов, контроль частоты деплоя |
| DNS TTL | Начать с TTL 300, потом 3600 |
| ACME abuse | Строгая валидация в `/api/tls/validate` |

## Связанные задачи

- [#31](https://github.com/urfu-online/apps-service/issues/31) — Caddy integration аудит
- [#28](https://github.com/urfu-online/apps-service/issues/28) — Валидация конфигурации
