# Дизайн-документ: перепроектирование platform CLI (v2)

> **УСТАРЕЛ.** Слит с [`platform-cli-product-design.md`](platform-cli-product-design.md)
> в единый документ [`platform-cli-v2-spec.md`](platform-cli-v2-spec.md) — там же
> зафиксированы решения по конфликтам между этими двумя документами (§19).
> Этот файл сохранён для истории обсуждения.

Бранч: `feature/cli-v2` (разработка с нуля рядом с текущей версией).
Статус: черновик на согласование.

---

## 1. Цель и контекст

Текущий platform CLI решает задачи, но с точки зрения UX это «10 разных скриптов»:
вывод вразнобой, нет интерактивности, нет автодополнения, диагностика живёт отдельными
скриптами в разных местах (`scripts/validate.py`, `docs/diagnostics/diagnose-*.sh`).

Решение по итогам интервью:

- CLI — **единая точка входа** для всего: управление сервисами, диагностика, бэкапы.
  Пользователь не должен ползать по истории терминала, вспоминая, что и как делалось.
- Целевая аудитория — и человек за терминалом, и скрипты/CI:
  интерактив по умолчанию, `--yes`/`--json` для автоматизации, строгие exit codes.
- Пишем **с нуля в отдельном бранче**, модульно. Доменная логика текущего кода
  переиспользуется (см. §4.3), CLI-слой переписывается.
- Командный интерфейс переразбивается по объектам (`platform service ...`),
  старые плоские команды не сохраняются.
- Дашборд (Textual) — отдельный этап после стабилизации основы.

Не входит в скоуп: изменение Master Service API (кроме согласованных дополнений,
см. §4.4), миграция `ops` bash-обёртки (перестаёт быть актуальной — всё в CLI).

---

## 2. Требования

### 2.1 Функциональные

| # | Требование |
|---|------------|
| F1 | Команды сгруппированы по объектам: `service`, `diag`, `backup`, `platform` |
| F2 | `status` — один экран по выбору: сервисы+роутинг, health-checks, ресурсы+бэкапы, сводка проблем; секции настраиваются конфиг-файлом |
| F3 | `deploy` — пошаговый прогресс: `→ build ✔ → up ✔ → healthcheck ✔ done in 12.4s`; падение шага — явное указание шага и причины |
| F4 | `logs` — подсветка (ERROR красным, WARN жёлтым, timestamps dim), фильтры `--since`/`--grep`, `--json` |
| F5 | `new` — интерактивный мастер (имя → public/internal → роутинг → порт/домен с валидацией) при отсутствии аргументов; с аргументами — молча, как раньше |
| F6 | Опциональные аргументы: не передал имя сервиса — интерактивный выбор (questionary, поиск по подстроке); `--yes` отключает вопросы; non-tty → BadParameter, не виснем |
| F7 | `diag` — втягивание `scripts/validate.py` и серверных диагностиек как подкоманд |
| F8 | Динамическое автодополнение имён сервисов/снапшотов с кэшем (TTL ~30с) |
| F9 | `--json` на всех читающих командах; единый формат ошибок (панель, не traceback) |
| F10 | `--watch` на status — живое обновление (rich.live), дашборд Textual — позже |
| F11 | Управляющие операции (deploy/stop/restart) должны работать при недоступном Master API |

### 2.2 Нефункциональные

- Строгие exit codes: `0` успех, `1` ошибка операции/сервиса, `2` ошибка аргументов,
  `3` недоступен зависимый компонент (docker/master), `4` сводка проблем не пуста (для `diag validate`).
- `NO_COLOR` / non-tty автоматически отключают украшения (rich делает это сам — не мешать).
- Ответность: completion-запросы ≤ ~100мс (кэш), `status` ≤ ~2с на 10 сервисов.
- Lock-механика (`platform_lock`) сохраняется — race conditions между CLI-вызовами недопустимы.
- Код ≥ Python 3.11 (как сейчас), ruff/black, линт-профиль переезжает из pyproject.

---

## 3. Дизайн-принципы вывода (единый визуальный язык)

1. **Всё печатается только через ui-слой.** Запрет прямого `console.print` в командах.
2. Одна рамка на всё приложение (`simple_heavy`), семантические цвета:
   green = ок, yellow = warn, red = ошибка, dim = второстепенное, bold cyan = объект.
3. Статусы — единые маркеры: `● running` / `● exited` / `● paused` / `? unknown`.
4. Сообщения: `ok()`, `fail()`, `step()`, `warn()`, `info()` — и никаких `✅/❌/ℹ️` эмодзи-строк в командах.
5. Таблицы — фабриками ui-слоя (`services_table`, `problems_table`, ...), команды только подают данные.
6. Ошибки API/докера — одной панелью через общий exception handler; traceback — только при `--verbose`.

---

## 4. Архитектура

### 4.1 Слои

```
┌─────────────────────────────────────────────────────────┐
│ cli.py — фабрика app: группы, completion, error handler │  (тонкий, без логики)
├─────────────────────────────────────────────────────────┤
│ commands/ — парсинг аргументов, оркестрация, вывод      │
│   service/  diag/  backup/  platform/                   │
├─────────────────────────────────────────────────────────┤
│ core/ — домен без CLI-зависимостей (переезд сущ. кода)  │
│   discovery, inspection, compose_runner, locks, config  │
├─────────────────────────────────────────────────────────┤
│ sources/ — доступ к данным (фасад для команд)           │
│   docker_source, caddy_source, master_source, cache     │
├─────────────────────────────────────────────────────────┤
│ ui/ — консоль, таблицы, панели, статусы, прогресс       │
└─────────────────────────────────────────────────────────┘
```

Зависимости направлены вниз. `core` не импортирует typer/rich — это обычная
библиотека, которую можно тестировать и переиспользовать (в т.ч. из master service
в будущем). Тесты патчат цели в `core`/`sources`, а не `apps_platform.cli.<helper>`.

### 4.2 Структура пакета

```
apps_platform/
├── cli.py                  # build_app(): Typer-фабрика, регистрация групп,
│                           # rich_markup_mode="rich", общий error handler
├── core/
│   ├── config.py           # ← config.py + cli-часть (get_project_root, get_config)
│   ├── discovery.py        # ← get_services() из cli.py
│   ├── inspection.py       # ← service_inspection.py (без переименований логики)
│   ├── caddy.py            # ← caddy_parser.py
│   ├── compose.py          # ← compose_cmd, get_service_status
│   ├── locks.py            # ← platform_lock
│   └── errors.py           # доменные исключения: ServiceNotFound, ComposeFailed, ...
├── sources/
│   ├── docker_source.py    # статусы/сети/статы/health через docker SDK+CLI
│   ├── caddy_source.py     # роутинг напрямую из conf.d/*.caddy (caddy рядом с мастером,
│   │                       #  живой и при падении master — разумно читать напрямую)
│   ├── master_source.py    # бэкапы и то, что умеет Master API (обёртка api_client)
│   └── cache.py            # TTL-кэш (~/.cache/platform-cli/*.json) для completion
├── ui/
│   ├── console.py          # Console, NO_COLOR, правила печати
│   ├── widgets.py          # таблицы, панели, статус-маркеры
│   ├── prompts.py          # pick_service(), confirm() — questionary, tty-чеки
│   └── progress.py         # пошаговый деплой-прогресс, Live-обёртка для --watch
├── commands/
│   ├── service/  (list, status, deploy, stop, restart, logs, new)
│   ├── diag/     (validate, server)
│   ├── backup/   (create, list, restore, delete)
│   └── platform/ (reload, info)
└── cli.py → main()
```

### 4.3 Переиспользование существующего кода

| Сейчас | Куда | Правки |
|---|---|---|
| `cli.py: get_project_root/get_config` | `core/config.py` | почти без правок |
| `cli.py: get_services()` | `core/discovery.py` | добавить возврат структурированных ServiceRef |
| `service_inspection.py` | `core/inspection.py` | убрать ре-экспорты для патчей тестов |
| `caddy_parser.py` | `core/caddy.py` | без правок |
| `compose_cmd`, `get_service_status` | `core/compose.py` | разделить: runner + статус |
| `platform_lock` | `core/locks.py` | без правок |
| `api_client.py` | `sources/master_source.py` | убрать импорт из `cli` (сейчас `from .cli import _get_ssl_verify`) |
| `scripts/validate.py` | `commands/diag/validate.py` + `core/validators/` | логика проверок → core, вывод → ui |
| `docs/diagnostics/diagnose-server.sh` (618) | `commands/diag/server.py` | поэтапно: сначала тонкий вызов, потом порт проверок в core |

### 4.4 Источники данных: правило выбора

Принцип: **сервисы управляются при неработающем master** → избыточную связность не
городим. Правило для каждого вида данных:

- **Управление контейнерами** (deploy/stop/restart/logs): docker/compose напрямую. Master API не участвует.
- **Discovery сервисов** (манифесты, директории): файловая система напрямую — это и есть источник правды.
- **Роутинг**: напрямую из `conf.d/*.caddy` (caddy живёт рядом с мастером и работает,
  в т.ч. когда master недоступен). Опционально, если мастер отдаст endpoint URL — переключить.
- **Health-checks**: если master их уже выполняет (HealthChecker, 30с интервал) — забираем
  из Master API кэшированные результаты; при недоступности мастера — прямые HTTP-пробы по `health.endpoint` из манифеста.
- **Бэкапы**: только Master API (Kopia за ним) — другого источника нет.
- **Ресурсы (память/диск/размер логов)**: docker SDK напрямую.

Источники сведены в фасад `sources/`, команды не знают, откуда пришла строка статуса.
Каждая читающая функция фасада деградирует независимо: master недоступен → секция
помечается `? master api недоступен`, остальное показывается.

---

## 5. Командный интерфейс

### 5.1 Реестр команд

| v2 | было | заметки |
|---|---|---|
| `platform service list` | `list` | таблица: имя, тип, статус, URL, последний деплой; `--json` |
| `platform service status [svc]` | `status` | см. §6 |
| `platform service deploy <svc>` | `deploy` | `--build --pull --dry-run --yes`; прогресс §7 |
| `platform service stop <svc>` | `stop` | `--yes`; подтверждение интерактивно |
| `platform service restart <svc>` | `restart` | |
| `platform service logs <svc>` | `logs` | `--lines --follow --since --grep --json` |
| `platform service new [name] [visibility]` | `new` | мастер при нехватке аргументов |
| `platform diag validate` | `scripts/validate.py` | те же проверки, exit 4 при проблемах |
| `platform diag server <svc-или-домен>` | `diagnose-server.sh` | имя ИЛИ домен; поэтапный порт |
| `platform backup create/list/restore/delete` | `backup` | через Master API |
| `platform platform reload` | `reload` | перезагрузка Caddy |
| `platform platform info` | `info` | + сводка проблем (строка-резюме) |

Опциональный аргумент `<svc>` везде: не передан → `ui.prompts.pick_service()`;
non-tty без аргумента → exit 2 с понятным сообщением.

### 5.2 Каркас cli.py

```python
def build_app() -> typer.Typer:
    app = typer.Typer(
        name="platform",
        rich_markup_mode="rich",
        pretty_exceptions_show_locals=False,   # в проде не сыпем локалами
        no_args_is_help=True,
    )
    app.add_typer(service_app, name="service", help="Жизненный цикл сервисов")
    app.add_typer(diag_app, name="diag", help="Диагностика и валидация")
    app.add_typer(backup_app, name="backup", help="Бэкапы (через Master API)")
    app.add_typer(platform_app, name="platform", help="Обслуживание платформы")
    app.add_exception_handler(AppError, app_error_handler)   # панель, exit 1
    return app
```

- Доменные исключения (`AppError` + подклассы из `core/errors.py`) — единственный
  путь ошибок наверх; обработчик печатает панель `✘ <сообщение>` + подсказку, exit по классу.
- `--verbose` и `--json` — общие опции колбэка.
- Установка: `install.sh` дополнить `platform --install-completion`.

### 5.3 Контракты для скриптов

- `--json` стабилен: не меняется между минорными версиями (документируем схему).
- exit codes из §2.2; `diag validate` в `--json` отдаёт структурированный отчёт.
- Прогресс-вывод деплоя в non-tty заменяется построчным логом (никаких `\r`-анимаций в пайпах).

---

## 6. Status-экран

Секции (каждая — независимый блок вывода, данные собираются из соответствующих источников):

| Секция | Источник | Что показывает |
|---|---|---|
| `services` | discovery + docker + caddy | имя, тип, статус-маркер, URL, версия/время деплоя |
| `health` | master → fallback direct | результат последнего health-check, время, ошибки |
| `resources` | docker stats + df | память по контейнерам, диск/размер логов |
| `backups` | master API | последний снапшот/возраст/размер по сервисам с backup.enabled |
| `problems` | агрегатор | см. ниже |

**Сводка проблем** — объединение лёгких проверок validate (см. §8) в режиме «только ошибки,
без фиксов»: visibility↔директория, routing без container_name, контейнер не в
platform_network, дубли доменов в caddy, кривые манифесты, недоступный master/caddy.
Резюме в конце: `3 проблемы у 2 сервисов → platform diag validate`.

Конфиг пользователя `~/.config/platform/config.yml`:

```yaml
status:
  sections: [services, health, problems]   # дефолт; полный набор: все 5
  compact: false
```

Секции можно перекрыть разово: `platform service status --sections services,resources`.
Неизвестная секция в конфиге — warn, не падение.

---

## 7. Деплой: пошаговый прогресс

Шаги: `preflight` (манифест найден, lock взят) → `build` (если `--build`) → `pull`
(если `--pull`) → `up` → `postcheck` (контейнеры подняты, health-проба).

```
→ preflight ✔
→ build    ✔ (28.1s)
→ up       ✔
→ postcheck ● health-check: 2/2 ok
✔ deployed in 31.2s
```

Реализация: `ui/progress.py` — таблица шагов со статусами, обновляемая по мере
прохода; сырой вывод docker compose показывается под текущим шагом (можно
подавить `--quiet`). Падение шага → красная строка с шагом, stderr в панели,
exit 1. `--dry-run` печатает план шагов без выполнения. non-tty → строки лога.

---

## 8. Diag

- `platform diag validate`: логика `scripts/validate.py` переносится: проверки →
  `core/validators/` (модуль на группу проверок: manifest, runtime, network, caddy),
  агрегатор возвращает `ValidationReport` (список findings: level, service, message, fix).
  Команда рендерит отчёт (человек) или JSON (скрипт), exit 4 при findings уровня error.
  Тот же `ValidationReport` переиспользуется секцией `problems` в status.
- `platform diag server`: сначала тонкая интеграция — вынести чтение манифеста по
  имени/домену и подготовку параметров в core, скрипт остаётся исполнителем;
  затем поэтапный порт проверок (docker/сети/пробы) в `core/validators/diag_*.py`.
  Старые bash-скрипты не удаляются до полного порта.

---

## 9. Completion и интерактив

- `shell_complete` для имён сервисов: из кэша `~/.cache/platform-cli/services.json`
  (TTL 30с; при устаревании — фоновое обновление, запрос не блокируется).
- `questionary` — новая зависимость (опрос/выбор/подтверждение, `use_search_filter=True`).
  Textual — в `[project.optional-dependencies] tui`, не в основных.
- Подтверждения деструктивных действий (`stop`, `backup restore`, `backup delete`):
  интерактивно по умолчанию, `--yes` — молча; в non-tty без `--yes` — exit 2.

---

## 10. План работ (фазы, каждая — рабочее состояние бранча)

| Фаза | Содержимое | Готовность |
|---|---|---|
| P1 | Скелет: структура пакета, `build_app()`, группы, ui-слой, перенос `core` (config/discovery/locks/compose), миграция тестов на новые цели патчей | команды v2 вызывают старую логику с новым выводом |
| P2 | `service list/status` с секциями и сводкой проблем; конфиг пользователя | читающий контур готов |
| P3 | `service deploy` с прогрессом, `stop/restart`, new-мастер | управляющий контур |
| P4 | `service logs` (подсветка, фильтры), `backup` через master_source | |
| P5 | `diag validate` (порт validate.py), completion + кэш | |
| P6 | `diag server` (порт bash-диагностики), `--watch` | |
| P7 | Textual dashboard (optional extra) | отдельное решение |

Каждая фаза: ruff + pytest зелёные; смок-тест на реальном сервере (`SERVICES_ROOT`/dry-run).
Удаление старого cli-слоя — после P5, когда v2 покрывает всё; до этого бранч
живёт параллельно, точка входа v2: `platform2` (внутри бранча) → в main переезжает как `platform`.

---

## 11. Открытые вопросы

1. `health` из master: нужен endpoint с результатами HealthChecker либо согласуем прямой опрос как основной. Влияет на §4.4 и секцию health.
2. «Последний деплой/версия» в списке сервисов: откуда взять честно — image digest контейнера vs файл-метка от deploy. Требует решения в P2.
3. Бэкапы в секции `resources`: достаточно «последний снапшот + возраст» или нужен полный список на экране?
4. `ops` bash-обёртка: объявить deprecated в README этого же бранча или оставить до P5.

---

## 12. Риски

- **Нестабильные docker-выводы** (`docker ps --format json` различается по версиям) — парсинг локализуем в `sources/docker_source.py`, тесты на фикстурах.
- **Эвристический caddy-парсер** (известные ограничения в докстринге) — не расширяем в этом бранче; дубли доменов проверяем поверх того, что он уже достаёт.
- **Тайминги**: health-пробы всех сервисов на каждый refresh `--watch` — только кэшированные результаты, прямые пробы не чаще 30с.
- **Lock-механика**: интерактивные мастера (new) держат lock дольше — blocking-wait с понятным сообщением вместо мгновенного exit.