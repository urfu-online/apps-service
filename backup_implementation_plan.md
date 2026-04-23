ПЛАН РЕАЛИЗАЦИИ ПОДСИСТЕМЫ РЕЗЕРВНОГО КОПИРОВАНИЯ (KOPIA EDITION)

Ключевые архитектурные решения
- Ядро: Kopia (отдельный сервис _core/kopia/)
- Хранилище: Локальный диск /data/kopia (конфигурируемо через KOPIA_STORAGE_TYPE, KOPIA_S3_*)
- Уведомления: Apprise → ntfy.sh (self-hosted) + Email fallback
- Планировщик: Python-координатор ТОЛЬКО триггерит kopia snapshot. Retention/Pruning делегирован политикам Kopia.
- Миграция: НЕ ВЫПОЛНЯЕТСЯ. Старые локальные бэкапы игнорируются. Чистый старт.
- Docker/ACL: Bind-mount ../../services:/services:ro. Для /data/kopia и staging используется entrypoint.sh с chown/chmod на старте контейнера.

Принципы реализации
- Поэтапная сдача (Phase 0→5) с валидацией после каждой
- Идемпотентность, секреты только в env, права 600/700
- Python-обёртка над bash-скриптами, а не реинжиниринг логики на Python
- Документация обновляется синхронно с кодом

🟦 Phase 0: Конфигурация, Модели и Секреты
Цель: Подготовить Pydantic-конфиг, SQLAlchemy-схему, валидацию секретов Kopia.
Задачи:
- Создать Pydantic BackupConfig: enabled, schedule (croniter validate), retention_days, paths, databases, kopia_policy (keep-daily/weekly/monthly)
- Валидатор: если enabled=True → проверка os.environ["KOPIA_REPOSITORY_PASSWORD"], иначе ValueError
- SQLAlchemy BackupRecord: id, service_name, snapshot_id (Kopia manifest), status, created_at, size_bytes, retention_days
- Удалить старые таблицы Backup/BackupSchedule/RestoreJob (или помечать deprecated)
- Интеграция с service.yml: парсер читает новый раздел backup
Файлы: _core/master/app/services/backup_models.py (новый), _core/master/app/models/backup.py, _core/master/app/main.py
Тесты:
  python -c "from app.services.backup_models import BackupConfig; print(BackupConfig(enabled=False).model_dump())"
  python -c "import os; os.environ.pop('KOPIA_REPOSITORY_PASSWORD', None); validate_backup_config(enabled=True)"

🟨 Phase 1: Kopia-сервис, ntfy.sh и Bash-обёртки
Цель: Поднять core-сервисы, создать идемпотентные CLI-скрипты, решить проблему прав Docker.
Задачи:
- _core/kopia/docker-compose.yml: образ kopia/kopia:latest, volumes: ../../services:/services:ro, /data/kopia:/repository, ./config:/kopia
- _core/kopia/entrypoint.sh: init репозитория (kopia repository create filesystem), chown -R 1000:1000 /repository /kopia, запуск kopia server start --disable-grpc
- _core/monitoring/ntfy/docker-compose.yml: binwiederhier/ntfy, auth-default-access: deny, юзер backup-bot с rw на топик backups
- Скрипты:
  • kopia_backup.sh: staging (tempfile), pg_dump/mysqldump → staging/db/, rsync → staging/fs/, kopia snapshot create --host {svc} --tags, вывод manifest_id в stdout
  • kopia_restore.sh: kopia restore {manifest_id} /target, разворот .sql дампа
  • kopia_policy.sh: kopia policy set --keep-daily=N --host {svc}
- Общие: set -euo pipefail, проверка бинарников, логирование в stderr, exit 0/1
Файлы: _core/kopia/..., _core/monitoring/ntfy/..., _core/backup/scripts/{backup,restore,policy,common}.sh
Тесты:
  export KOPIA_REPOSITORY_PASSWORD=testpass
  bash _core/backup/scripts/kopia_backup.sh test-svc /tmp/staging
  kopia snapshot list --repository /data/kopia --password-file <(echo testpass)

🟧 Phase 2: Python-координатор и Планировщик
Цель: Связать cron из service.yml с Kopia, делегировать retention, запустить уведомления.
Задачи:
- Рефакторинг BackupManager: убрать старую логику, добавить asyncio.create_subprocess_exec для вызова скриптов Phase 1
- async run_backup(svc): mkdtemp → backup.sh → парсинг manifest_id → запись BackupRecord → Apprise.notify("backup.completed")
- async enforce_retention(svc): проверка политики в БД → вызов kopia_policy.sh → обновление статуса
- Планировщик (events.py/lifespan): asyncio.sleep(60) + croniter.next() → триггер run_backup() если due
- dry_run=True: логирует команды, не запускает процессы и не пишет в БД
Файлы: _core/master/app/services/backup_manager.py, _core/master/app/core/events.py
Тесты:
  pytest tests/unit/test_backup_manager.py -k "test_dry_run_backup" -v
  python -c "import asyncio; from app.services.backup_manager import BackupManager; asyncio.run(BackupManager(dry_run=True).run_backup('test-svc'))"

🟥 Phase 3: API, CLI и Синхронизация Состояния
Цель: Endpoints для управления, команды platform, валидация перед restore/delete.
Задачи:
- API: POST /backups/{svc}/backup, GET /backups/{svc}, POST /backups/{svc}/restore/{id}, DELETE /backups/snapshot/{id}
- Валидация: запрет restore/delete если контейнер запущен (или --force), проверка существования manifest_id через kopia snapshot list --json
- CLI: platform backup <svc> [--dry-run], platform backup list <svc>, platform restore <svc> <id>
- Интеграция: CLI → API через requests, вывод Rich-таблиц/прогресса
Файлы: _core/master/app/api/routes/backups.py, _core/platform-cli/apps_platform/cli.py, api_client.py (новый)
Тесты:
  curl -X POST http://localhost:8000/api/backups/test-svc/backup
  platform backup list test-svc

🟪 Phase 4: NiceGUI UI и Уведомления (Apprise)
Цель: Рабочие кнопки, статусы, polling, безопасная отправка событий.
Задачи:
- Таблица бэкапов: ID, Created, Status (🟢/🟡/🔴), Size, Actions. Polling 5s
- Кнопки: Create (spinner → API), Restore (диалог → API), Delete (подтверждение → API)
- AppriseNotifier: инициализация из NOTIFY_URLS="ntfy://backup-bot:pass@ntfy:8086/backups, mailto://user:pass@smtp/internal@ops"
- События: backup.completed, backup.failed, restore.completed → apprise.async_notify()
- Безопасность UI: скрытие RESTIC_/KOPIA_ переменных, стриппинг логов, проверка прав
Файлы: _core/master/app/ui/backups_page.py, _core/master/app/services/notifier.py
Тесты:
  docker compose up -d → http://localhost:8001/backups
  Проверка: создание обновляет таблицу, restore требует подтверждения, ntfy принимает событие

🟩 Phase 5: Обновление Документации
Цель: Синхронизировать все гайды с новой архитектурой, убрать упоминания Restic/Telegram.
Задачи:
- docs/user-guide/backup.md: заменить rsync/pg_dump → Kopia, Telegram → ntfy.sh/Apprise, добавить примеры KOPIA_* env
- docs/user-guide/monitoring.md: обновить раздел уведомлений, добавить ntfy.sh endpoint
- TROUBLESHOOTING.md: раздел "Проблемы с бэкапами" → Kopia CLI, kopia manifest list, ntfy topicks
- ai_summary.md: обновить стек, диаграммы, статусы компонентов
- Проверка битых ссылок, консистентности env-переменных
Файлы: docs/, README.md, ai_summary.md, TROUBLESHOOTING.md
Тесты:
  mkdocs build --strict
  grep -r "restic\|telegram" docs/ → пусто (кроме исторических примечаний)

Порядок выполнения и валидации
Phase 0 → тест → коммит
Phase 1 → тест → коммит
Phase 2 → тест → коммит
Phase 3 → тест → коммит
Phase 4 → тест → коммит
Phase 5 → линтер/docs → коммит
Финал: интеграционный тест (ручной запуск backup → появление в Kopia → отправка в ntfy → restore из UI)

Дополнительные соображения
- Хранение: /data/kopia по умолчанию. Переключение на S3/SFTP через KOPIA_STORAGE_TYPE без правок кода
- Права Docker: entrypoint.sh решает проблему root-владелца. Альтернатива: setfacl -d -m u:1000:rwX /data/kopia на хосте
- Миграция: намеренно пропущена. Старые backups/ помечаются как deprecated в UI
- Мониторинг: kopia maintenance run добавляется в cron хоста или отдельный systemd timer для проверки целостности репозитория