# Backlog: platform-cli P1 «Каркас»

Вход для developer'а. Технические детали — в `01_tech_spec_p1_scaffold.md`.
Каждая задача самодостаточна; порядок — по фазам, внутри фазы параллельные
группы (WIP ≤ 3).

**Выполнено до старта фазы (не задачи бэклога):**
- **T0**: v1 `apps_platform/cli.py` → `legacy_cli.py` (git mv; импорты
  commands/*, api_client, tests, pyproject переключены; baseline тестов
  25 failed/71 passed = прекестовый, rename нейтрален).
- Правка спеки: §12.4 + code `command_moved` (exit 2), ревизия 1.3.
- **Hotfix T1**: `PlatformError` — frozen-поля + разрешён setattr служебных
  атрибутов исключения (`__traceback__` и пр.): Typer/contextlib ставит
  `exc.__traceback__`, иначе все ошибки v2 превращались в `internal_error`
  (находка T7); обход `_CommandMovedError` в заглушках снят.
- **Известный долг v1 (baseline, 25 падений, НЕ чинить в P1)**:
  `test_api_client` ×14 (патч AsyncMock ClientSession не срабатывает) +
  `test_cli` ×11 (коллайдер `backup`-команды/группы в v1, `129_chars`).
  Диагностировано 2026-10-06; удаляется вместе с v1 в P7.

## Легенда

- ⛓️ — обязательные предпосылки (должны быть готовы до старта)
- 📄 — файлы
- ✅ — критерии приёмки
- 🚫 — границы (вне задачи)
- 🧪 — тесты
- 📝 — документация в рамках задачи
- `[parallel]` — можно брать одновременно с соседями в группе

---

## Фаза P1.1 — Контракты (ядро)

### T1. `core/errors.py` — PlatformError и закрытый реестр кодов `[parallel]`

| Поле | Значение |
|---|---|
| **Что сделать** | Создать `apps_platform/core/errors.py`: `PlatformError(code, message, object, hint, cause)` и закрытый реестр `code → exit → hint` из спеки §12.4; классификация неожиданных исключений |
| **Детали** | `PlatformError` — frozen dataclass; поле `exit_code` вычисляется из реестра по `code` (задаётся вызывающим нельзя). Реестр — неизменяемая константа (mapping/desk dataclass): все коды §12.4 (`arg_missing` … `internal_error`) + новый `command_moved` (exit 2) для заглушек §7.5. Фабрики/помощники: `wrap_unexpected(exc) -> PlatformError` (`internal_error`, exit 1), `cancelled() -> PlatformError` (exit 130). Хелпер `to_json()` ошибки: объект `{schema_version, error: {code, message, object, hint}}` |
| **⛓️ Зависимости** | нет |
| **📄 Файлы** | новые: `apps_platform/core/__init__.py`, `apps_platform/core/errors.py`, `tests/test_errors.py` |
| **✅ Критерии приёмки** | каждый code из §12.4 присутствует ровно один раз; exit по каждому code совпадает со спекой; `command_moved` → 2; `wrap_unexpected` → 1; `cancelled` → 130; попытка неизвестного code — AssertionError/KeyError; pytest зелёный |
| **🚫 Границы** | без вывода (print/console), без Typer/Rich, без текстов сообщений команд (только реестр и механика) |
| **🧪 Тесты** | полнота реестра против таблицы §12.4 (список кодов в тесте); маппинг code→exit; `to_json` содержит `schema_version` |
| **📝 Документация** | docstring модуля: «единственный владелец exit-кодов; новые коды — только через ADR-ревью» |

### T2. `core/models.py` — доменные типы и Deadline `[parallel]`

| Поле | Значение |
|---|---|
| **Что сделать** | Создать `apps_platform/core/models.py`: базовые типы данных по §10.4 и скелет дедлайна по ADR-001 |
| **Детали** | `ServiceRef` (name, path, visibility, routing); enums: `Visibility {public, internal, core}`, `Routing {domain, subfolder, port, none}`, `SectionState {complete, partial, unavailable}`, `FindingLevel {error, warning, note}`, `ObservationSource {filesystem, docker, caddy, master, direct_probe}`; `Observation`, `Finding`, `FixSuggestion` (description, root_cause, commands: list[list[str]], risky) — контракты §10.4 дословно; `Deadline`/`DeadlinePolicy` (budget_s, `remaining()`, на monotonic-часах) — скелет, применяется с P2. Всё frozen dataclass / Enum, без поведенческой логики |
| **⛓️ Зависимости** | нет |
| **📄 Файлы** | новые: `apps_platform/core/models.py`, `tests/test_models.py` |
| **✅ Критерии приёмки** | все типы frozen/immutability; поля совпадают с §10.4 (включая отсутствие поля `warnings` у `SectionResult` — предупреждения это `Finding`); `Deadline.remaining()` уменьшается и не уходит ниже 0; pytest зелёный |
| **🚫 Границы** | без `SectionResult`/`ValidationReport`/`DeploymentResult` (появляются в P2+ с use cases); без валидации и I/O |
| **🧪 Тесты** | неизменяемость полей (попытка присвоения падает); значения enum; поведение `Deadline` |
| **📝 Документация** | docstring'и полей, соответствующие §10.4 |

### T3. `core/ports.py` — 8 Protocols

| Поле | Значение |
|---|---|
| **Что сделать** | Создать `apps_platform/core/ports.py`: восемь `typing.Protocol` из ADR-002 (ServiceDiscovery, DockerReader, CaddyReader, MasterGateway, HealthProber, LockManager, CacheStore, Journal) |
| **Детали** | Сигнатуры P1 — по таблице §4 tech spec: `ServiceDiscovery.list_services() -> list[ServiceRef]` — полный контракт; остальные порты — минимальная заготовка (runtime_checkable, один метод-заглушка или пустое тело протокола), методы наполняются в P2–P4. `@runtime_checkable` для проверок в тестах. Новый порт запрещён (закрытый список) |
| **⛓️ Зависимости** | T2 (ServiceRef, enums) |
| **📄 Файлы** | новые: `apps_platform/core/ports.py`, `tests/test_ports.py` |
| **✅ Критерии приёмки** | ровно 8 портов; импорт портов не тянет Typer/Rich/docker/requests; fake-класс в тесте проходит `isinstance`-проверку runtime_checkable; pytest зелёный |
| **🚫 Границы** | без реализаций адаптеров (это T6); без добавления девятого порта |
| **🧪 Тесты** | fake-реализация каждого порта собирается и проходит Protocol-проверку; проверка, что `core.ports` не импортирует внешние библиотеки (smoke: импорт модуля в чистом окружении / grep импортов) |
| **📝 Документация** | docstring на каждом Protocol: какой адаптер и какая фаза наполняют |

### T4. `config.py` — §11.1 приоритеты, env, AppConfig

| Поле | Значение |
|---|---|
| **Что сделать** | Перенести логику резолвинга корня и конфига из `cli.py` в `apps_platform/config.py` (поведение не меняется) и расширить под §11.1: приоритеты, env-переменные, frozen `AppConfig`, user config |
| **Детали** | Цепочка project root: `--project-dir` → `OPS_PROJECT_ROOT` → маркер `.ops-root` → `project_root` из системного конфига → CWD (5 уровней, §11.1; уровень 1 — новый). Приоритет настроек: CLI-флаг > env > user config (`${XDG_CONFIG_HOME:-~/.config}/platform/config.yml`, только preferences) > `.ops-config.yml` (+`.ops-config.local.yml` deep-merge). `AppConfig` frozen: `root`, `ops_config` (dict), `master_url` (дефолт `http://localhost:8001`), `ssl_verify` (политика `PLATFORM_ENV`/`PLATFORM_SSL_VERIFY`), `user_prefs` (sections/deadline/stale_after — schema объявлен, значения по умолчанию), `api_token` (из env, никогда не печатается). Отсутствующий ops-конфиг → `PlatformError(config_not_found)` из T1. В `legacy_cli.py`: старые `get_project_root()`/`get_config()` становятся делегатами к config (v1 работает как раньше) |
| **⛓️ Зависимости** | T1 (PlatformError) |
| **📄 Файлы** | изменённые: `apps_platform/config.py`, `apps_platform/legacy_cli.py` (только делегаты), `tests/test_config.py`; новый: `tests/test_config_v2.py` |
| **✅ Критерии приёмки** | все 5 уровней root-резолвинга покрыты тестами; приоритеты настроек соблюдены (таблица §11.1); `config_not_found` → exit 3; v1-тесты `tests/test_config.py` и `tests/test_cli.py` зелёные после делегатов; `PLATFORM_ENV=production` → verify=True всегда; pytest зелёный |
| **🚫 Границы** | без `--verbose`/`--json` и прочих глобальных опций (это T8); без использования токена (P2); без чтения `status.sections`-потребителей (P2) |
| **🧪 Тесты** | каждый уровень цепочки root; deep-merge local-override; env-политика SSL; отсутствие конфига → ошибка T1; **без патчей** внутренних имён — через env/monkeypatch `os.environ` и tmp_path |
| **📝 Документация** | docstring `config.py`: таблица приоритетов; обновить докстринги делегатов в `cli.py` |

---

## Фаза P1.2 — Реализация (параллельно после P1.1)

### T5. `ui/` — console и реестр рендереров text/json `[parallel]`

| Поле | Значение |
|---|---|
| **Что сделать** | Создать `apps_platform/ui/console.py` и `apps_platform/ui/renderers/` с рендерерами text/json, реестром по типу результата и политикой каналов/цвета |
| **Детали** | `RenderedOut(stdout: str, stderr: str)` frozen (в `ui/renderers/__init__.py` или `ui/__init__.py`). Реестр `dict[type, Renderer]` + `register()`/`get()`; `get()` для незарегистрированного типа — AssertionError. Политика вывода: цвета отключаются при `NO_COLOR`, `TERM=dumb`, `--no-color`, non-TTY stdout — независимо для каждого канала. JSON-рендерер ошибок: объект `{schema_version: 1, error: {...}}` через `PlatformError.to_json()` (T1). Text-рендерер ошибок: 4 вопроса §12.3 (что/объект/что успели/что дальше), hint в конце |
| **⛓️ Зависимости** | T1 (PlatformError), T2 (модели) |
| **📄 Файлы** | новые: `apps_platform/ui/__init__.py`, `apps_platform/ui/console.py`, `apps_platform/ui/renderers/__init__.py`, `apps_platform/ui/renderers/text.py`, `apps_platform/ui/renderers/json.py`; `tests/test_renderers.py` |
| **✅ Критерии приёмки** | `render()` чистые: не печатают, возвращают `RenderedOut`; реестр по типу результата; JSON всегда объект с `schema_version` и только в `stdout`; текст ошибки — в `stderr`; цвета гаснут при `NO_COLOR`/non-TTY; pytest зелёный |
| **🚫 Границы** | без NDJSON (P4); без таблиц/виджетов status (P2); без печати (print только в `cli.py`); без регистрации рендереров (registration — в T8) |
| **🧪 Тесты** | golden-вывод text-ошибки (ширина 60/80/120); JSON-ошибка валиден и парсится; `NO_COLOR`/`TERM=dumb`/non-TTY — по отдельности; `stdout`/`stderr` не смешиваются |
| **📝 Документация** | docstring контракта рендерера («форматирование только здесь») |

### T6. `sources/` — скелет адаптеров (обёртки над v1) `[parallel]`

| Поле | Значение |
|---|---|
| **Что сделать** | Создать пакет `apps_platform/sources/`: `filesystem.py` (реализация ServiceDiscovery) + обёртки/скелеты остальных 8 модулей, реализующих порты T3 |
| **Детали** | `filesystem.list_services()` — обёртка над `cli.get_services()` → `list[ServiceRef]` (visibility: core/public/internal из пути; routing пока `absent`/дефолт, заполняется P2); резолвинг корня берётся из `config.py` (T4). `locks.py`, `compose.py`, `docker.py` — делегирование к существующим функциям `cli.platform_lock`/`compose_cmd`/`get_service_status`/`service_inspection` с конверсией `typer.Exit` и текстовых ошибок в `PlatformError` (коды по §11.2: `docker_unavailable`, `lock_busy` — exit 3). `master.py` — тонкая обёртка над `api_client` (get_api_client), без rewrite. `caddy.py`, `probe.py`, `cache.py`, `journal.py` — скелеты, реализующие Protocol с `NotImplementedError`-заглушками (используются только после наполнения в своих фазах) |
| **⛓️ Зависимости** | T3 (порты), T4 (config), T1 (ошибки) |
| **📄 Файлы** | новые: `apps_platform/sources/__init__.py`, `filesystem.py`, `docker.py`, `caddy.py`, `master.py`, `probe.py`, `compose.py`, `locks.py`, `cache.py`, `journal.py`; `tests/test_sources.py` |
| **✅ Критерии приёмки** | каждый модуль реализует свой Protocol (runtime_checkable isinstance); ни один модуль не импортирует `cli.py`/`legacy_cli`, Typer и не делает print; `filesystem.list_services()` возвращает `ServiceRef` на реальной структуре сервисов (fixtures `services/{public,internal}` и `_core`); v1-тесты зелёные (v1-код не менялся сверх делегатов T4); pytest зелёный |
| **🚫 Границы** | без переноса логики из v1 (обёртки, не релоцирование; pure/IO разделение — P2); без rewrite master на requests (P2); без scoped locks (P3); без journal format (P4) |
| **🧪 Тесты** | fake-`Ctx` со всеми адаптерами собирается; обёртки конвертируют `typer.Exit` → `PlatformError`; `list_services()` на tmp-структуре директорий; скелеты бросают `NotImplementedError` |
| **📝 Документация** | docstring каждого модуля: «обёртка над <v1-модуль>, логика переезжает в Pn» |

### T7. `commands/legacy.py` — заглушки старых команд §7.5 `[parallel]`

| Поле | Значение |
|---|---|
| **Что сделать** | Создать `apps_platform/commands/legacy.py` (v2): скрытые команды-заглушки, перехватывающие плоские вызовы v1: `deploy`, `stop`, `restart`, `logs`, `backup`, `new`, `list`, `reload`, `status`-дубль |
| **Детали** | Позиционные аргументы принимаются и игнорируются (любые). Ответ — `PlatformError(command_moved, …)` из T1 (exit 2) с текстом по образцу §7.5: «Команда изменена в platform v2 / Было: … / Стало: … / Подсказка: platform --help; заглушки будут удалены в v2.1». Маппинг «было → стало»: `deploy→service deploy`, `stop→service stop`, `restart→service restart`, `logs→service logs`, `backup→backup …`, `new→service create`, `list→service list`, `reload→proxy reload`, `status`-дубль→`status`. Заглушки не регистрируются в help (скрытые команды Typer). `--json` на заглушке → JSON-ошибка `command_moved` в stdout |
| **⛓️ Зависимости** | T1 (реестр, `command_moved`) |
| **📄 Файлы** | новые: `apps_platform/commands/legacy.py`, `tests/test_legacy.py`; изменён: `apps_platform/core/errors.py` только если code `command_moved` добавляется здесь (иначе T1 уже добавил) |
| **✅ Критерии приёмки** | каждая из 9 заглушок отвечает exit 2 и точным текстом §7.5; ни одна заглушка не появляется в `platform2 --help`; `--json` даёт валидный объект ошибки в stdout; pytest зелёный |
| **🚫 Границы** | без реализации новых команд (P2+); без deprecated-сообщения для `ops` (P7); без удаления заглушек |
| **🧪 Тесты** | параметризованный тест на все 9 заглушок (exit 2, текст «Было/Стало»); отсутствие в help (в T10 subprocess); JSON-вариант |
| **📝 Документация** | docstring: «заглушки живут весь v2.x, удаление — только мажорная версия (§7.5)» |

---

## Фаза P1.3 — Интеграция

### T8. `cli.py` — composition root, entry `platform2`, общие опции в любой позиции

| Поле | Значение |
|---|---|
| **Что сделать** | Создать новый `apps_platform/cli.py` (v1 уже переименован в `legacy_cli.py` — T0): `Ctx`, сборка зависимостей, фабрика Typer-приложения, preprocessing argv для общих опций, точка входа `main()`; добавить entry point в `pyproject.toml` |
| **Детали** | `Ctx` frozen dataclass по §3 tech spec (config, root, deadline_policy, 8 адаптеров из T6, renderers-реестр, global_opts). Сборка: `build_ctx(global_opts) -> Ctx` — единственное место, знающее concrete adapters; в `build_ctx` — assertion, что для всех зарегистрируемых типов результатов есть рендереры. Общие опции (§7.4): `--verbose --json --no-input --yes --no-color --project-dir PATH` — собираются **до и после подкоманды** (preprocessing argv: вырезать глобальные опции из argv, применить к `GlobalOpts`, остаток отдать Typer; ограничение Click обходится явно, как требует §7.4). `--verbose` → logging DEBUG; `--json` → implies `--no-input`. Регистрация: заглушки T7; в help — группа команд-заготовок не выводится (команды P2+ добавят себя). Exception boundary: любой необработанный exception → `wrap_unexpected` → рендер → exit; `KeyboardInterrupt` → `cancelled` → 130. `platform2 = "apps_platform.cli:main"` в `[project.scripts]` |
| **⛓️ Зависимости** | T1, T2, T3, T4, T5, T6, T7 |
| **📄 Файлы** | новые: `apps_platform/cli.py`, `tests/test_ctx.py`; изменённые: `pyproject.toml` |
| **✅ Критерии приёмки** | `pip install -e .` даёт команду `platform2`; `platform2 --help` работает; `platform2 --json deploy api` и `platform2 deploy api --json` эквивалентны (опции в любой позиции); `Ctx` frozen, адаптеры типизированы портами (mypy/pyright по желанию, минимум — аннотации); отсутствие рендерера = AssertionError при сборке (тест); pytest зелёный |
| **🚫 Границы** | без data-команд (P2); без completion (P5); без изменения v1 entry `platform`; без `questionary` |
| **🧪 Тесты** | `build_ctx` с fake-адаптерами; позиционная инвариантность общих опций; `--verbose` включает debug-лог; `--json` отключает prompt-поведение (no_input=True); assertion-путь без рендерера; subprocess: `platform2 --help` exit 0 |
| **📝 Документация** | docstring `build_ctx` как composition root; комментарий к preprocessing argv со ссылкой на §7.4 |

### T9. Единый exception boundary и маршрутизация вывода

| Поле | Значение |
|---|---|
| **Что сделать** | Завершить error mapping в `cli.py`: `PlatformError` → рендерер (text → stderr / json → stdout) → exit code из реестра; unexpected → `internal_error` + traceback при `--verbose`; Ctrl-C → 130 без traceback |
| **Детали** | Один обработчик на всё приложение (никаких try/except в командах). Порядок: перехватить → `PlatformError` (или `wrap_unexpected`) → получить рендерер ошибки из реестра → `RenderedOut` → записать stdout/stderr → `sys.exit(code)`. Traceback (только `--verbose`, только stderr): chaining через `cause`. Ранние ошибки конфигурации (нет ops-конфига до сборки рендереров) — минимальный фолбэк-рендер в том же модуле, но тот же JSON-контракт. Секреты (`api_token`) не попадают ни в один поток (§16) |
| **⛓️ Зависимости** | T1, T5, T8 |
| **📄 Файлы** | изменённые: `apps_platform/cli.py`; `tests/test_errors.py` (расширение) |
| **✅ Критерии приёмки** | каждый exit code P1-сценариев: 0 (help), 2 (заглушка/аргументы), 3 (config_not_found), 1 (unexpected), 130 (Ctrl-C, тест через subprocess с сигналом); JSON-ошибка — валидный объект в stdout; текстовая ошибка — stderr, stdout пуст; traceback отсутствует без `--verbose` и присутствует с ним; pytest зелёный |
| **🚫 Границы** | без интерактива/подтверждений (P3); без `no_tty`-сценариев мутаций (P3 — но `--json` implies `--no-input` уже в T8) |
| **🧪 Тесты** | таблица «сценарий → exit, канал, формат»; subprocess с SIGINT → 130; unexpected exception → 1 и без traceback в stderr по умолчанию |
| **📝 Документация** | docstring boundary: «единственный место exit-кодов приложения» |

### T10. CLI subprocess-тесты P1 (критерий выхода фазы)

| Поле | Значение |
|---|---|
| **Что сделать** | Набор subprocess-тестов через реальный entry `platform2`, закрывающий exit criteria P1 §18.1: help, exit codes, stdout/stderr, TTY/non-TTY, `--json`-ошибки |
| **Детали** | Запуск `platform2` как отдельного процесса (`subprocess`/`typer.testing.CliRunner` только там, где не нужен реальный TTY). Покрыть: (1) `--help`/`-h` exit 0, заглушки отсутствуют; (2) таблица exit codes: 0/1/2/3/130 по сценариям T7/T9; (3) разделение каналов: JSON → stdout-only (парсится, `schema_version`), текст ошибки → stderr; (4) TTY: через `pty.openpty()` — prompt/цветевые выводы идут в stderr, в stdout их нет; non-TTY: цвета отключены (`NO_COLOR` учитывается); (5) `--json`-ошибки на всех P1-сценариях; (6) общие опции в любой позиции; (7) NO_COLOR / `TERM=dumb` / `--no-color`. Golden-снапшоты текстового вывода (help, ошибка заглушки) при стабильной ширине |
| **⛓️ Зависимости** | T7, T8, T9 |
| **📄 Файлы** | новый/расширяемый: `tests/test_cli_v2.py`; фикстуры: `tests/fixtures/` (tmp-проект с `.ops-root`, `.ops-config.yml`, `services/*`) |
| **✅ Критерии приёмки** | каждый пункт §18.1-P1 (help, exit codes, stdout/stderr, TTY/non-TTY, `--json`-ошибки) покрыт минимум одним тестом; тесты детерминированы (tmp_path, без docker/сети); полный `pytest` зелёный; `ruff check` и `black --check` зелёные |
| **🚫 Границы** | без интеграционных тестов с реальным Docker/Caddy (P2+); без smoke на прод-сервере (в конце фаз P2+) |
| **🧪 Тесты** | это и есть задача-тесты; каждый тест — отдельный сценарий с явными ожиданиями exit/канал/тело |
| **📝 Документация** | краткий `tests/README.md`: как запускать subprocess-тесты, зачем фикстуры |

### T11. Интеграционное ревью и стабилизация P1

| Поле | Значение |
|---|---|
| **Что сделать** | Ревью собранного каркаса против принципов tech spec (раздел 10) + прогон всего контура качества; закрытие критериев выхода фазы |
| **Детали** | Проверить и исправить: (1) слоистость — `core/` не импортирует Typer/Rich/docker/requests (grep импортов по пакетам); (2) отсутствие print/console вне `cli.py` и `ui` при финальном выводе; (3) отсутствие патчей внутренних имён в новых тестах (только подмена портов через `Ctx`); (4) v1 не сломан: `pytest tests/test_cli.py tests/test_config.py tests/test_api_client.py` зелёные; (5) exit criteria T10 выполнен; (6) русский текст человеку / английский полям (§7.6). Артефакт: список найденных и исправленных отклонений в описании PR |
| **⛓️ Зависимости** | T1–T10 (все) |
| **📄 Файлы** | любые из P1 по результатам ревью; `pyproject.toml` (per-file-ignores при необходимости) |
| **✅ Критерии приёмки** | `ruff check .`, `black --check .`, `pytest` — зелёные; grep-проверки слоистости чистые; exit criteria P1 §18.1 подтверждены прогоном T10; замечания ревью закрыты; (4) v1 не сломан: `tests/test_cli.py`, `tests/test_config.py`, `tests/test_api_client.py` — **не хуже baseline**: допустимы ровно 25 прекестовых падений (`test_api_client` ×14 — патч ClientSession не перехватывает создание сессии; `test_cli` ×11 — коллайдер имён плоского `backup <svc>` и группы `backup create` + `test_rejects_129_chars`; известный долг v1, вне P1, удаляется с v1 в P7); новых падений — 0 |
| **🚫 Границы** | без рефакторинга сверх найденных отклонений; без новых функций; без обновления README (P7) |
| **🧪 Тесты** | полный прогон всего сьюта — регрессия P1 |
| **📝 Документация** | описание PR: что покрывает P1, что измерено критериями выхода |

---

## Граф зависимостей

```text
T1 errors ──┬──────────────┬──► T7 legacy ─────────────┐
            │              │                           │
T2 models ──┴─► T3 ports ──┴──► T6 sources ────────────┤
                                                       ├──► T8 ──► T9 ──► T10 ──► T11
T4 config ──────────────► T6 sources                   │
T4 config ─────────────────────────────────────────────┘
T1 errors ──┬──► T5 ui ──────────────────────────────► T8
T2 models ──┘
```

## Параллельные группы (WIP ≤ 3)

| Группа | Задачи | Предпосылки |
|---|---|---|
| Фаза P1.1 | T1, T2 ∥ T4 (T3 после T2) | — |
| Фаза P1.2 | T5, T6, T7 ∥ | фаза P1.1 |
| Фаза P1.3 | T8 → T9 → T10 → T11 (последовательно) | фаза P1.2 |

## Критический путь

```text
T2 → T3 → T6 → T8 → T9 → T10 → T11
```

Самая длинная цепочка; T1/T4/T5/T7 — питатели с большим запасом
(параллельны критическому пути).
