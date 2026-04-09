# Loki / Prometheus / Grafana

## Проблема

Документация ссылается, кода нет. Директория `_core/monitoring/` удалена.

Это **не баг**, а отдельная фича. Не блокирует текущую работу.

## Подход

Решить: нужен ли полноценный monitoring stack или достаточно того, что есть:
- Health checks (работают)
- Docker API логи (работают через `DockerManager.get_logs`)
- Telegram уведомления (работают)
- NiceGUI dashboard (работает)

Если да — отдельный проект с docker-compose для Loki + Promtail + Prometheus + Grafana.

## Папка

`./10-monitoring-stack/`
