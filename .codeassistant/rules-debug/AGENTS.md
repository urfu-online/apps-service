# AGENTS.md – Правила для режима Debug

## Типичные ошибки и их решения
- **Caddy не перезагружает конфиг**: изменения в шаблонах требуют вызова API CaddyManager (`/api/caddy/reload`)
- **Health checks не работают**: проверьте, что `service.yml` содержит `health_check.endpoint` (строка, например `/health`)
- **Сервис не обнаружен**: убедитесь, что манифест лежит в `services/public/` или `services/internal/` и имеет оба файла `service.yml` + `docker-compose.yml`
- **Platform CLI не работает**: он должен быть установлен в изолированном venv (`_core/platform-cli/.venv`), не в глобальном

## Диагностика окружения
- **Логи Caddy**: `_core/caddy/logs/` (но файлы могут быть пустыми, если не настроен logging)
- **Логи master service**: вывод `make dev` или журнал Docker контейнера
- **Состояние health checks**: эндпоинт `/api/health/checks` возвращает статусы всех сервисов
- **Проверка генерации конфигов**: `_core/caddy/conf.d/` содержит сгенерированные файлы (но они могут перезаписываться)

## Команды для отладки
- `make test` – запуск unit-тестов (быстрая проверка)
- `make test-cov` – тесты с покрытием, помогает найти непокрытый код
- `docker compose -f _core/master/docker-compose.dev.yml logs` – логи dev-окружения
- `curl -X POST http://localhost:2019/load -H "Content-Type: text/caddyfile" --data-binary @Caddyfile` – ручная перезагрузка Caddy (если API не работает)

## Интеграционные тесты и DinD
- Интеграционные тесты используют Docker-in-Docker; убедитесь, что Docker socket доступен (`/var/run/docker.sock`)
- Полный цикл развертывания (`test_full_deploy_cycle`) может занимать несколько минут
- При падении интеграционных тестов проверьте, что все необходимые образы загружены

## Отладка BackupManager
- Расписания задаются через croniter; проверьте корректность cron-выражения в `service.yml`
- Бэкапы используют rsync (локально) или pg_dump (для PostgreSQL); убедитесь, что целевые директории существуют
- Логи бэкапов можно найти в `backups/` (если настроено)