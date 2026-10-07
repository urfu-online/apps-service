# Backlog: platform-cli P2 «Наблюдение»

Вход для developer'а. Технические детали — в `02_tech_spec_p2_observation.md`
(ссылки на спеку v2 — `platform-cli-v2-spec.md`). Каждая задача
самодостаточна; порядок — по фазам, внутри фазы параллельные группы
(WIP ≤ 3). Точка входа в бранше — `platform2`.

## Легенда

- ⛓️ — обязательные предпосылки (должны быть готовы до старта)
- 📄 — файлы
- ✅ — критерии приёмки
- 🚫 — границы (вне задачи)
- 🧪 — тесты
- 📝 — документация в рамках задачи
- `[parallel]` — можно брать одновременно с соседями в группе

---

## Фаза P2.1 — Контракты (ядро)

### T1. `core/models.py` — модели наблюдения: секции, статусы, отчёты

| Поле | Значение |
|---|---|
| **Что сделать** | Расширить `apps_platform/core/models.py`: статусные enum'ы (Прил. D), факты контейнеров, типы строк секций, `SectionResult`, `ValidationReport`, `StatusReport`, `ServiceCatalog`/`CatalogEntry`, `InfoReport` |
| **Детали** | Enum'ы §3.1 tech spec: `ServiceState {running,degraded,starting,restarting,not_deployed,exited,unhealthy,crash_loop,unknown}`, `HealthState {ok,failing,unknown,not_configured,not_applicable}` — машинные значения дословно из §3.1. Типы §3.2: `ContainerFact` (id, name, compose_project, labels, state, health, exit_code, restart_count, networks→IP, published_ports, mem_usage/mem_limit/log_size), `ProbeTarget` (host, port, kind http/tcp, path), `HealthResult` (state, reason, source, observed_at, stale, history). Типы §3.3: `SectionResult` (state, data, observations, findings — §10.4 дословно, поля `warnings` нет), `ValidationSummary`, `ValidationReport`, `StatusSummary` (services_total, services_running, attention, problems), `StatusReport` (scope, complete, sections, summary, sources, elapsed_s), `ServiceStatusRow`, `HealthRow`, `ResourceRow`, `BackupRow`, `CatalogEntry`, `InfoReport`, `DependencyStatus`. `ServiceRef` расширяется: `RoutingEntry` (type, domain, base_domain, path, port, internal_port, container_name, auto_subdomain), `ServiceManifest` (routing: tuple[RoutingEntry,…] \| None, routing_none: bool, health_endpoint, backup_enabled) — контракт Прил. B. Всё frozen dataclass / StrEnum, без поведенческой логики |
| **⛓️ Зависимости** | нет (на базе моделей P1) |
| **📄 Файлы** | изменить: `apps_platform/core/models.py`, `tests/test_models.py` |
| **✅ Критерии приёмки** | все новые типы frozen; enum-значения совпадают с §3.1 tech spec; `SectionResult` без поля `warnings`; `HealthResult.unknown` допускает `reason`; `ServiceManifest` различает «routing забыт» (None) и «routing: none» (routing_none); pytest зелёный |
| **🚫 Границы** | без алгоритмов сопоставления/агрегации (T2), без I/O и валидации значений, без JSON-сериализации (to_json — в рендерерах, T11) |
| **🧪 Тесты** | неизменяемость новых типов; значения enum против таблицы §3.1; конструирование `SectionResult`/`StatusReport` с минимальным набором полей |
| **📝 Документация** | docstring'и типов со ссылками на § tech spec; в `core/models.py` — нормализация машинных значений `not_deployed`/`crash_loop` (§3.1 п.6) |

---

## Фаза P2.2 — Источники и проверки (параллельные группы, WIP ≤ 3)

### T2. `core/matching.py` — сопоставление контейнер ↔ сервис §11.6.1 `[parallel]`

| Поле | Значение |
|---|---|
| **Что сделать** | Создать `apps_platform/core/matching.py`: чистый алгоритм сопоставления контейнеров сервисам (§11.6.1) и агрегации `ServiceState` (§4.2 tech spec) |
| **Детали** | Вход `list[ContainerFact]` + `list[ServiceRef]` → `list[ServiceMatch]` + несопоставленные. Приоритет: (1) `com.docker.compose.project == имя`; (2) метка `platform.service == имя`; (3) эвристика имён v1 (`_matches_service`: нормализация дефисов/подчёркиваний, суффикс `-1`, префиксы compose) — перенос логики из v1 как чистая функция, v1-файл не трогать. Контейнер — максимум одному сервису, переназначение запрещено. Агрегация состояния — таблица §4.2 (приоритет: not_deployed → crash_loop (restart_count ≥ 5, константа `CRASH_LOOP_RESTARTS`) → unhealthy → restarting → starting → exited → degraded → running → unknown+причина) |
| **⛓️ Зависимости** | T1 |
| **📄 Файлы** | новые: `apps_platform/core/matching.py`, `tests/test_matching.py` |
| **✅ Критерии приёмки** | кейсы §11.6.1 покрыты: `urfu_forms_backend` → urfu-forms, `course-archive-explorer-frontend-1` → course-archive-explorer, `support-zammad-web` → support; compose-project приоритетнее метки, метка — эвристики; несопоставленные контейнеры не порождают сервисы; агрегация по таблице §4.2 (все кейсы); pytest зелёный |
| **🚫 Границы** | без обращения к Docker/ФС (только чистые функции); без вывода |
| **🧪 Тесты** | параметризованные кейсы сопоставления (фикстуры имён/меток из Прил. F.2); приоритеты шагов 1–3; краевой случай: контейнер подходит под два сервиса; все переходы агрегации состояний |
| **📝 Документация** | docstring: владелец правила §11.6.1; константа `CRASH_LOOP_RESTARTS` — с пояснением |

### T3. `sources/filesystem.py` — полный манифест, каталог сервисов, `SERVICES_ROOT` `[parallel]`

| Поле | Значение |
|---|---|
| **Что сделать** | Наполнить `FilesystemDiscovery`: разбор `service.yml` → `ServiceRef` + `ServiceManifest` (Прил. B), URL-правило §4.4, офлайн-каталог, env `SERVICES_ROOT` |
| **Детали** | Чтение манифеста сервисов `services/{public,internal}/*` + core (порядок v1: core, public, internal). Поля Прил. B: name (regex `[a-z0-9][a-z0-9_-]{0,62}`, равен каталогу), visibility (совпадает с каталогом — расхождение не парсится здесь, это finding в T8), routing (список записей / `none` / забытое поле), health.endpoint, backup. URL-правило §4.4: domain → `https://<domain>`, subfolder → `https://<base_domain><path>`, port → `порт <port>` (URL отсутствует), none → «(порт-сервис, HTTP-роутинга нет)», забытое поле → URL отсутствует. **Никаких URL из caddy**. `SERVICES_ROOT` — переопределение каталога `services/` (tests/dev, §18.2). Структурированный возврат `ServiceCatalog`/`list[ServiceRef]` — без вывода |
| **⛓️ Зависимости** | T1 |
| **📄 Файлы** | изменить: `apps_platform/sources/filesystem.py`, `apps_platform/core/ports.py` (сигнатура `ServiceDiscovery` — по §5.1 tech spec); `tests/test_sources.py` |
| **✅ Критерии приёмки** | каталог по фикстурам Прил. F: imap-proxy (`routing: none`) → «(порт-сервис, HTTP-роутинга нет)», никаких `http://localhost:8000`; мусорные строки caddy не влияют на URL (caddy вообще не читается); `SERVICES_ROOT` переключает корень сканирования; битый манифест не роняет весь каталог (сервис пропускается с пометкой для T8); pytest зелёный |
| **🚫 Границы** | без Docker/caddy/master; без Finding'ов (валидация — T8); без фильтра `--visibility` (это T10) |
| **🧪 Тесты** | манифесты фикстур (все routing-типы + none + забытое поле); URL-таблица §4.4; `SERVICES_ROOT`; name-regex (валидные/невалидные) |
| **📝 Документация** | docstring модуля: «единственный источник ServiceRef/URL; правило §4.4» |

### T4. `sources/docker.py` — DockerReader: факты, сети, stats `[parallel]`

| Поле | Значение |
|---|---|
| **Что сделать** | Реализовать адаптер `DockerReader`: пакетный сбор `ContainerFact` (все контейнеры одним батчем), engine-инфо, stats для секции `resources`; деградация Docker недоступен |
| **Детали** | Сигнатуры §5.1 tech spec: `container_facts() -> list[ContainerFact]`, `service_stats() -> list[ResourceRow]` (память по **всем** контейнерам — регрессия §11.6.3⁵), `engine_info() -> DependencyStatus`. Сбор: `docker ps -a --format json` + `docker inspect` батчем / `docker stats --no-stream` (subprocess argv-массивом с timeout, либо docker SDK — внутри адаптера); чистые парсеры вывода — в `core` (перенос логики `service_inspection`, v1-файл не трогать). Недоступность docker → `PlatformError(code=docker_unavailable)` либо типизированный отказ источника, который use case мапит в `Observation` (матрица §11.2: status — секция partial/unavailable, не exit; info — отчёт) |
| **⛓️ Зависимости** | T1 |
| **📄 Файлы** | изменить: `apps_platform/sources/docker.py`, `apps_platform/core/ports.py`; новый pure-парсер (в `core/`); `tests/test_sources.py`, фикстуры вывода docker |
| **✅ Критерии приёмки** | факты содержат compose-метки, метки `platform.*`, сети→IP, published ports, restart_count, health, mem/log-поля; один батч-инвокация на сбор (не N запросов); память/логи по каждому контейнеру; docker недоступен — типизированный отказ без traceback; pytest зелёный |
| **🚫 Границы** | без сопоставления сервисам (T2), без пробы (T6), без mutation-команд (compose up/down — P3); v1 `service_inspection.py` не менять |
| **🧪 Тесты** | парсеры на фикстурах `docker ps`/`inspect`/`stats` из прод-среза (Прил. F.2: 15 контейнеров, имена с подчёркиваниями/суффиксами); обработка отсутствия полей; отказ docker |
| **📝 Документация** | docstring: контракт `DockerReader`, бюджет времени на вызов, деградация §11.2 |

### T5. `core/caddy_parse.py` + `sources/caddy.py` — маршруты conf.d `[parallel]`

| Поле | Значение |
|---|---|
| **Что сделать** | Разделить чистый парсер и I/O чтения caddy-конфигов: pure-парсер в `core/caddy_parse.py` (перенос логики `parse_caddy_config`), чтение `conf.d/*.caddy` → `sources/caddy.py` (`CaddyReader.routes() -> list[CaddyRoute]`) |
| **Детали** | `CaddyRoute(domain, path, upstream, source_file)` — §5.1 tech spec. Парсер — чистые функции над строками/текстом (без Path-I/O): домен, path, upstream. Адаптер читает файлы `conf.d/*.caddy` (по путям ops-конфига; фикстуры — прод-срез). Цель использования в P2 — проверки T8 (`caddy/duplicate-domain`, `caddy/orphan-route`); URL из caddy не вычисляются никогда (§4.4). v1 `caddy_parser.py` не трогать |
| **⛓️ Зависимости** | T1 |
| **📄 Файлы** | новые: `apps_platform/core/caddy_parse.py`; изменить: `apps_platform/sources/caddy.py`, `apps_platform/core/ports.py`; `tests/test_sources.py`, фикстуры `caddy-conf.d` |
| **✅ Критерии приёмки** | парсер выделяет domain/path/upstream из прод-конфигов (включая строки-мусор вида `https://tls`, `https://@sentry` — без превращения их в URL сервисов); адаптер возвращает `CaddyRoute[]` с source_file; отсутствие каталога conf.d → пустой список + `Observation`-причина на уровне use case; pytest зелёный |
| **🚫 Границы** | без проверок (T8), без admin API Caddy (это P6), v1-модуль не менять |
| **🧪 Тесты** | pure-парсер на текстовых фикстурах (нормальные сайты, мусорные строки, дубли доменов); адаптер на файловых фикстурах |
| **📝 Документация** | docstring: «чистый парсер перенесён из caddy_parser (§10.5); владельцы — §4.4 URL-правило» |

### T6. `sources/probe.py` — HealthProber: прямая проба (Q6) `[parallel]`

| Поле | Значение |
|---|---|
| **Что сделать** | Реализовать `HealthProber.probe(ProbeTarget) -> HealthResult` по стратегии Q6 (§4.3 tech spec) |
| **Детали** | HTTP: `GET <path>` к primary-цели (IP контейнера + internal_port), fallback — published port (`127.0.0.1:<host_port>`); 2xx → `ok`, иначе → `failing` (reason: код/отказ/timeout). TCP-connect для порт-сервисов (`routing: none` / запись `port`): успех → `not_applicable`, отказ → `failing`. Таймаут пробы `min(2s, остаток deadline)`; вызов — только в адаптере (socket/HTTP-клиент); `HealthResult` несёт source=`direct_probe`, observed_at, stale=false. Обогащение Master (история) — не в этой задаче |
| **⛓️ Зависимости** | T1 |
| **📄 Файлы** | изменить: `apps_platform/sources/probe.py`, `apps_platform/core/ports.py`; `tests/test_sources.py` |
| **✅ Критерии приёмки** | `ok/failing/not_applicable` по правилам §4.3; fallback на published port при недоступном IP контейнера; timeout уважается (не зависает); `HealthResult` всегда заполнен source/observed_at; pytest зелёный |
| **🚫 Границы** | без определения целей из манифеста/docker (это use case T9); без history/кэша Master (T7); `--watch`-пороги проб — P4 |
| **🧪 Тесты** | HTTP 2xx/5xx/refused/timeout (локальные сокеты/фикстуры); TCP успех/отказ; fallback-логика; уважение таймаута |
| **📝 Документация** | docstring: стратегия Q6 (primary/fallback), семантика `not_configured`/`not_applicable` |

### T7. `sources/master.py` — MasterGateway на requests, деградация `[parallel]`

| Поле | Значение |
|---|---|
| **Что сделать** | Реализовать `MasterGateway` (§5.1 tech spec) синхронным клиентом на `requests`: `info() -> MasterInfo`, `health_snapshot() -> HealthSnapshot \| None`, `last_backups() -> list[BackupRow]`; полная деградация при недоступном Master |
| **Детали** | URL/TLS/токен — из `AppConfig` (§11.1; токен только env, не логируется, §16). `info()` — версия/доступность/API-версия; сравнение major-версии → `compatible` (§15 tech spec, п.2). `health_snapshot()` — путь обогащения §11.6.4: роута может не быть → `None` + причина (никаких fake-историй). `last_backups()` — последний снапшот на сервис (возраст, размер) для секции `backups`; существующие роуты Master API backup (как в v1 `api_client`, но без его импорта). Отказ: `MasterInfo(available=False, note=…)`, `None`, пустой список — с причиной; use case переводит в `Observation`/`unavailable` (матрица §11.2: для status — warning, не exit 3). Синхронность (ADR-001); бюджет времени на запрос (timeout); ретраев нет (одна попытка на вызов) |
| **⛓️ Зависимости** | T1 |
| **📄 Файлы** | изменить: `apps_platform/sources/master.py`, `apps_platform/core/ports.py`, `pyproject.toml` (только если нужен импорт-реестр v2-модуля; зависимости не менять); `tests/test_sources.py` |
| **✅ Критерии приёмки** | v2 не импортирует `api_client`/aiohttp; отказ сети/DNS/таймаут — типизированный, без traceback; `health_snapshot` при 404 → `None` (не ошибка команды); токен не попадает в repr/логи/вывод; pytest зелёный |
| **🚫 Границы** | без backup-команд (P4) и journal (P4); без изменения v1 `api_client.py`; без ретраев/кэширования (кэш — P5) |
| **🧪 Тесты** | fake HTTP (ответы/отказы/таймаут/404 на health-snapshot); `MasterInfo.compatible` при разных major; `last_backups` по фикстурам ответа; отсутствие токена в текстах ошибок |
| **📝 Документация** | docstring: деградация §11.2, заглушка §11.6.4, что history не показывается без источника |

### T8. `core/validators/` — лёгкие проверки → Finding (manifest, runtime, network, caddy)

| Поле | Значение |
|---|---|
| **Что сделать** | Создать `apps_platform/core/validators/` (manifest.py, runtime.py, network.py, caddy.py + реестр `__init__.py`): чистые проверки → `Finding[]` с `FixSuggestion`; подмножество для секции `problems` — §3.4 tech spec |
| **Детали** | Реестр: check-id → уровень + cost (§3.4). `manifest/*`: missing, invalid-yaml, name-mismatch, visibility-dir (два корректных fix'а: `mv` каталога `risky: true` / смена visibility), routing (забытое поле → warning «задайте routing: none…»; `routing: none` → note), routing-entry (container_name/internal_port), health-endpoint. `runtime/running`, `network/external`, `network/membership` (fix — корневая причина в compose + `docker network connect` как временное `risky: true`), `caddy/duplicate-domain`, `caddy/orphan-route`, `platform/labels` (note). Вход — только собранные факты (ServiceRef/Manifest, ServiceMatch, ComposeFacts, CaddyRoute[]); I/O запрещено. `FixSuggestion.commands` — argv-массивами, пути от current project root, никогда не исполняются (§9.4). Подмножество `problems` (§15.1) помечено в реестре флагом `in_problems` |
| **⛓️ Зависимости** | T1, T2 (для runtime/network — факты сопоставления) |
| **📄 Файлы** | новые: `apps_platform/core/validators/{__init__,manifest,runtime,network,caddy}.py`, `tests/test_validators.py` |
| **✅ Критерии приёмки** | каждый check-id §3.4 существует ровно один раз, уровень и cost совпадают; fix'ы — argv-массивы, не строки shell; `manifest/visibility-dir` содержит оба варианта fix'а, `mv` помечен risky; `network/membership` fix содержит корневую причину; подмножество `problems` строго §15.1; pytest зелёный |
| **🚫 Границы** | без CLI `diag validate` (фильтры/`--fail-on`/ignore-list — P5); без HTTP-проб; без вывода; scripts/validate.py не трогать |
| **🧪 Тесты** | по каждому check-id: срабатывание и негативный кейс; структура FixSuggestion (argv, risky, root_cause); подавление не предусмотрено (ignore-list — P5) |
| **📝 Документация** | docstring каждого check-id: условие, уровень, fix; реестр — таблица §3.4 со ссылкой |

---

## Фаза P2.3 — Сценарии и вывод

### T9. `commands/status.py` — StatusUseCase: секции, deadline, partial

| Поле | Значение |
|---|---|
| **Что сделать** | Создать `apps_platform/commands/status.py`: тонкий Typer-обработчик + `StatusUseCase`; команда `platform2 status [SERVICE]` c `--sections LIST`, `--strict`, `--json` |
| **Детали** | Сбор §4.5 tech spec: параллельный опрос портов через `ThreadPoolExecutor` (N10) с **общим** deadline (`UserPrefs.deadline_s`, 2s); мэтчинг §11.6.1 (T2) → `ServiceState`; health-пробы (T6) с целями из манифеста+фактов docker; обогащение Master (T7), секции `backups`/источники по матрице §9 tech spec; `problems` — строго подмножество T8; `resources` — только при явном `--sections resources`. Секции → `SectionResult` (state/observations/findings); `complete: false` при любой не-complete секции; «требует внимания» и шапка `N из M … K` — формула §4.2. `--sections`: канонический порядок печати, неизвестная → `section_unknown` exit 2; scope-сервис: `service_not_found` exit 2; `--strict` + unavailable-секция → exit 3 (partial — exit 0). Подсказки «Следующий шаг» (§8 tech spec). Результат — `StatusReport`; никакого print в use case (P1-принципы) |
| **⛓️ Зависимости** | T2, T3, T4, T6, T7, T8 |
| **📄 Файлы** | новый: `apps_platform/commands/status.py`; изменить: `apps_platform/cli.py` (регистрация команды), `tests/test_cli_v2.py`, `tests/test_status.py` |
| **✅ Критерии приёмки** | `platform2 status` без аргументов — непустой обзор всех сервисов (регрессия §11.6.3¹); `--sections services,health` — только они; неизвестная секция → exit 2 + hint; `--strict` при недоступном Docker → exit 3; без `--strict` → exit 0 + partial + причина; status никогда не prompt'ит (non-TTY без `--yes` не спрашивает); Master недоступен — секции services/problems полные, backups unavailable (C1 по толкованию §2 tech spec); pytest зелёный |
| **🚫 Границы** | без `--watch` (P4), без вывода (рендеры — T11), без мутаций и locks, без `diag validate` CLI |
| **🧪 Тесты** | use case на fake-портах через `Ctx`: полный сбор; отказ каждого опционального источника (матрица §11.2: partial/unavailable/complete-флаги); истечение deadline (partial, причина); формула attention; scope одного сервиса; exit-коды 0/2/3 |
| **📝 Документация** | docstring use case: матрица §11.2, политика exit §8.3, канонический порядок секций |

### T10. `commands/service.py` (list) + `commands/platform_ops.py` (info)

| Поле | Значение |
|---|---|
| **Что сделать** | Создать `commands/service.py` с `platform2 service list [--visibility …]` (офлайн-каталог) и `commands/platform_ops.py` с `platform2 info` (единственная сводка окружения) |
| **Детали** | `list`: только ФС (T3) — имя, VIS, роутинг, URL из манифеста; фильтр `--visibility {public,internal,core}`; результат `ServiceCatalog`; быстрый (бюджет как у completion-базы); `--json` — схема §7 tech spec. `info`: `InfoReport` (cli_version, project_root + источник резолвинга, пути ops-config/user-config/cache/locks, зависимости: Docker Engine/Compose/Caddy/Master (T4/T5/T7 `engine_info`/`info()`), окружение: NO_COLOR/TERM/PLATFORM_ENV/ssl_verify/запуск из контейнера). `info` — **всегда exit 0** (несовместимость Master — в отчёте, не exit). Обработчики тонкие, use case без print |
| **⛓️ Зависимости** | T3, T4, T7 |
| **📄 Файлы** | новые: `apps_platform/commands/service.py`, `apps_platform/commands/platform_ops.py`; изменить: `apps_platform/cli.py` (регистрация), `tests/test_catalog.py`, `tests/test_cli_v2.py` |
| **✅ Критерии приёмки** | list без Docker работает и быстрый; URL-мусор caddy недостижим (регрессии ², ⁴: imap-proxy → «(порт-сервис, HTTP-роутинга нет)»); `--visibility` фильтрует; info при полностью мёртвом окружении → exit 0 с причинами по каждой зависимости; info — единственное место сводки версий (F14); pytest зелёный |
| **🚫 Границы** | без `create/deploy/logs/backup` (P3–P4), без `proxy reload` (P3), без journal-записей (P4); группы `service`/`platform_ops` расширяются позже |
| **🧪 Тесты** | каталог по фикстурам Прил. F (включая все 6 регрессий ²/⁴ через URL-правило); фильтр visibility; info: частичная доступность зависимостей, всегда exit 0; JSON-схемы (§7 tech spec) |
| **📝 Документация** | docstring'и команд; help Typer (опции, примеры) |

### T11. `ui/renderers` — статус/каталог/info: text + json, виджеты, golden

| Поле | Значение |
|---|---|
| **Что сделать** | Реализовать рендереры `StatusReport`, `ServiceCatalog`, `InfoReport` (text + json) и виджеты: таблицы, статус-маркеры Прил. D, компактный режим; golden-снапшоты 60/80/120 |
| **Детали** | Text: экран §9.1 дословно (шапка `[<источники>, <Ns>]`, таблица SERVICE/VIS/STATUS/ROUTING-URL, Health с provenance, Problems, «Несобрано: …», «Следующий шаг»); компакт `platform2 status <SVC>` (§4); маркеры/цвета/текст-дубли — таблица §3.1 tech spec; узкий терминал/`compact` — компактное представление (§5.6). Инкрементальный режим status в TTY (секции по мере готовности, канонический порядок, финальная страница с шапкой) и batch для non-TTY/`--json` — §2 п.3 tech spec; печатает только `cli.py`, рендереры возвращают `RenderedOut`/их последовательность (ADR-003). Json: схемы §7 tech spec, `schema_version: 1`, корень-объект, `ValidationReport`-вид для findings с `cost`. `NO_COLOR`/`TERM=dumb`/`--no-color`/non-TTY — без цвета (§12.1) |
| **⛓️ Зависимости** | T1 (типы результатов) |
| **📄 Файлы** | изменить: `apps_platform/ui/renderers/{text,json}.py`, `apps_platform/ui/renderers/__init__.py` (реестр), новый `apps_platform/ui/widgets.py`; `tests/test_renderers.py`, `tests/fixtures/golden/` |
| **✅ Критерии приёмки** | golden-снапшоты status (полный/частичный/один сервис), list, info — ширины 60/80/120 + NO_COLOR; статус-маркеры и текст-дубли совпадают с §3.1; в `--json` нет human-текста в stdout; колонки без данных не рисуются (регрессия ⁶); pytest зелёный |
| **🚫 Границы** | без NDJSON (P4), без прогресса деплоя (P3), без prompt'ов (P3); содержимое схем не менять против §7 tech spec |
| **🧪 Тесты** | golden-снапшоты на фиксированных результатах (fake-данные секций); различия text/json; поведение при отсутствующих полях (нет колонки); инкрементальный порядок секций |
| **📝 Документация** | docstring рендереров: канонический порядок секций, таблица маркеров §3.1 |

---

## Фаза P2.4 — Интеграция и регрессия

### T12. Фикстуры прода, матрица деградации, JSON-схемы, регрессии v1

| Поле | Значение |
|---|---|
| **Что сделать** | Материализовать фикстуры прод-среза 2026-10-06 (Прил. F) и закрыть критерии выхода фазы тестами: матрица §11.2, JSON-схемы, 6 регрессий §11.6.3 |
| **Детали** | `tests/fixtures/prod-2026-10-06/`: docker-ps.jsonl, docker-inspect/stats-срезы, caddy-conf.d/*.caddy (с мусорными строками F.3²), manifests/*.yml (включая imap-proxy `routing: none`, забытые поля), ожидаемые выводы. По ним — CLI subprocess-тесты (реальный запуск `platform2`, stdout/stderr/exit): (1) status без аргумента непустой (F.3¹); (2) URL-мусор отсутствует, чужие URL не утекают (F.3²); (3) urfu-forms не «stopped» при живых контейнерах (F.3³); (4) imap-proxy без `localhost:8000` (F.3⁴); (5) память по всем контейнерам (F.3⁵); (6) нет `Available: ?`-колонок (F.3⁶). Матрица §11.2: для каждой команды P2 × источник (ФС/Docker/Caddy/Master) — набор «источник падает → поведение секции/exit». JSON-схемы: обязательные поля, `schema_version`, корень-объект, полнота `complete`-флага; TTY/non-TTY |
| **⛓️ Зависимости** | T9, T10, T11 |
| **📄 Файлы** | новые: `tests/fixtures/prod-2026-10-06/**`, `tests/test_regressions_v1.py`, `tests/test_degradation.py`; изменить: `tests/test_cli_v2.py` |
| **✅ Критерии приёмки** | все 6 регрессий §11.6.3 закрыты зелёными тестами на прод-фикстурах; матрица §11.2 покрыта (каждая команда P2 × каждый источник); JSON-валидация всех трёх команд (включая partial-ответы); golden-вывод стабилен на 60/80/120; pytest зелёный |
| **🚫 Границы** | без нагрузочных/бюджетных замеров (T13); без тестов P3+ (Ctrl-C subprocess, логи, backup); без правки продуктового кода — кроме найденных дефектов (тогда фикс отдельным коммитом в задаче) |
| **🧪 Тесты** | сама задача — тестовая; структура: unit (фикстуры) + CLI subprocess (exit/stdout/stderr/JSON) |
| **📝 Документация** | README фикстур: происхождение среза (Прил. F), как обновлять ожидаемые выводы |

### T13. Интеграционное ревью P2, smoke на реальном сервере, бюджеты N1

| Поле | Значение |
|---|---|
| **Что сделать** | Интеграционное ревью фазы + финальная проверка P2 на реальном сервере (§18.2 п.7): smoke `platform2 status`/`service list`/`info` с `SERVICES_ROOT`; замер бюджетов N1; стабилизация; правка текста сценария C1 по толкованию §2 tech spec |
| **Детали** | Ревью: диффы всех задач P2 против tech spec (модели §3, матрица §9, JSON-схемы §7, принципы §14) — расхождения устраняются в задаче. Smoke: запуск против реального `/apps` (read-only команды; мутаций нет) со сверкой против ожиданий Прил. F (10 сервисов, 15 контейнеров). Бюджеты: status ≤ 2с на 10 сервисов (дедлайн соблюдён → partial корректен), старт CLI ≤ 150мс (ленивые импорты сохранены). Baseline v1-тестов «не хуже» (25 failed — прекестовый, не чинить). Ruff/black — по CONTRIBUTING. Правка `platform-cli-v2-spec.md` Прил. C1 (health при мёртвом Master — по §2 tech spec) + запись в журнал решений (Прил. A) |
| **⛓️ Зависимости** | T12 |
| **📄 Файлы** | изменить: `docs/platform-cli-v2-spec.md` (C1, Прил. A — правка формулировок), тесты при необходимости; smoke-скрипт не создаётся |
| **✅ Критерии приёмки** | smoke на реальном сервере пройден (статус/list/info без traceback, provenance виден); бюджет status ≤ 2с подтверждён замером; старт CLI ≤ 150мс; pytest: новых падений относительно baseline 0; C1 отражает толкование §2 |
| **🚫 Границы** | без деплоя/мутаций на сервере; без performance-оптимизаций сверх бюджета; без P3-кода |
| **🧪 Тесты** | smoke-проверки — команды вручную/скриптом на сервере; бюджеты — замер времени запуска; детерминированные тесты остаются в T12 |
| **📝 Документация** | правка C1/Прил. A спеки; итоговая сводка фазы в конце backlog не нужна — статус фиксируется в памяти проекта |

---

## Граф зависимостей

```text
T1 ──┬── T2 ── T8 ──┐
     ├── T3 ────────┤
     ├── T4 ────────┼── T9 ──┐
     ├── T5 ──┬─────┤        │
     ├── T6 ──┤     ├── T10 ─┼── T12 ── T13
     ├── T7 ──┴─────┤        │
     └── T11 ───────┴────────┘
```

- T2–T7, T11 — после T1; T8 — после T2; T9 — после T2, T3, T4, T6, T7, T8;
  T10 — после T3, T4, T7; T12 — после T9, T10, T11; T13 — после T12.

## Параллельные группы (WIP ≤ 3)

| Волна | Задачи | Примечание |
|---|---|---|
| P2.1 | T1 | одна задача — контракты, дальше все зависят |
| P2.2 волна 1 | T2, T3, T4 | брать одновременно |
| P2.2 волна 2 | T5, T6, T7 | брать одновременно |
| P2.2 волна 3 | T8 | после T2 |
| P2.3 | T11, затем T9, T10 | T11 можно брать параллельно с T9/T10 после готовности типов |
| P2.4 | T12, T13 | строго последовательно |

## Критический путь

**T1 → T2 → T8 → T9 → T12 → T13**
