# Детальная страница сервиса в UI

## Проблема

`_core/master/app/ui/services_page.py` или роутинг в `main.py`:

- `/services/{service_name}` → `RedirectResponse("/services")`
- Компоненты `ServiceCard` и `LogViewer` существуют, но не используются

## Подход

Реализовать страницу:
- Информация о сервисе (версия, тип, visibility, routing)
- Статус контейнеров (CPU, RAM из `DockerManager.get_stats`)
- Логи (inline LogViewer)
- Кнопки: deploy, stop, restart, backup
- История деплоев

## Папка

`./6-service-detail-page/`
