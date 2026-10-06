# Platform CLI v2 — Product Requirements Document (PRD)

> Версия: PRD-слой v1.1
> Дата: 2026-10-06 · Статус: **влит в спеку v1.2** (Приложения G/H) —
> `platform-cli-v2-spec.md` является итоговым ТЗ; дальнейшие правки PRD не
> вносятся. Исправления ревью (AC-F014-01, C6, MoSCoW-арифметика,
> AC-F012-01, отказ≠Ctrl-C, F-017/US, backup US/AC) внесены в v1.1.
> Связь с техдизайном: каждый пункт PRD ссылается на разделы авторитетной
> спеки (`Platform CLI v2: сводный дизайн-документ`). Техдизайн этим
> документом **не заменяется и не изменяется** — PRD добавляет продуктовые
> слои: personas, user stories, MoSCoW, acceptance criteria, риски, метрики.

---

## 1. Overview

### 1.1 Background & Motivation

Текущий platform CLI — это «10 разных скриптов, собранных в один бинарник»:
вывод вразнобой, нет автодополнения и интерактивности, диагностика живёт
отдельными bash-скриптами (validate.py, diagnose-*..sh), а `list`/`status`/
`logs` показывают лишь часть картины. Оператор вынужден помнить внутренние
helper'ы и листать историю терминала. (Спека §1.1)

### 1.2 Objectives

| Тип | Цель |
|---|---|
| Пользовательская | Оператор за один запуск `platform status` понимает: что работает, что сломано, почему и какой следующий шаг (цикл Observe → Explain → Act → Verify, спека §4) |
| Пользовательская | Разработчик сервиса проходит цикл create → deploy → verify → logs без знания Master API |
| Пользовательская | CI-скрипт получает JSON-контракт, строгие exit codes и гарантию отсутствия prompt'ов |
| Бизнесовая | Единая точка входа для всего операционного взаимодействия с платформой; уход от разрозненных скриптов без ломания существующих cron/runbooks (заглушки, спека §7.5) |

**Success metrics (допущение PRD-слоя — в спеке не зафиксированы):**

| Метрика | Цель | Базовая линия |
|---|---|---|
| Время до диагноза оператором (запуск → понимание проблемы) | ≤ 30 секунд, 1 команда | Историю терминала + 3–4 скрипта |
| Доля операций, выполняемых через CLI (не через прямые docker/скрипты) | ≥ 80% за 3 месяца после релиза | ~0% (скрипты вне CLI) |
| Бюджеты производительности (спека §17.1) | status ≤ 2с · completion ≤ 100мс p95 · старт CLI ≤ 150мс | не измерялись |
| CI-гейт `diag validate` | зелёный на чистой платформе, красный при error-findings | validate.py ad-hoc |

### 1.3 Scope

**In scope (v1):** перестройка пакета `apps_platform` (структура, ui-слой,
каркас команд), перенос диагностики, JSON/NDJSON-контракты, exit codes,
locks, completion, мастера. Минимальные необязательные дополнения Master API.

**Out of scope (v1, явный Won't Have):**

- Изменение Master Service как продукта (спека §1.3)
- `service delete` — ручная операция (тома, реестр манифестов, caddy)
- Автофикс конфигурации / флаг `--fix` — только текстовые fix-подсказки (§5.8)
- Порт `diagnose-client.sh` — другая среда, остаётся скриптом (§15.4)
- Textual dashboard — отложено до отдельного документа по реальному опыту (§1.2)

---

## 2. User Personas

| Persona | Описание | Роль | Core Goal | Primary Pain Point |
|---|---|---|---|---|
| **Оператор платформы** | Дежурит платформу, отвечает за аптайм | SRE / DevOps | За один обзор понять состояние и следующий шаг | Собирает картину из 4–5 источников вручную |
| **Разработчик сервиса** | Деплоит и дебажит свой сервис | Backend-разработчик | Короткий повторяемый цикл create→deploy→logs | Должен помнить имена сервисов, флаги, внутренние helper'ы |
| **CI / скрипт / cron** | Машинный потребитель | GitHub Actions, cron, runbooks | Надёжно выполнить операцию и определить результат | Текстовый вывод непарсабелен, prompt'ы ломают пайплайны |

Все три persona используют одни сценарии и модели данных — два presenter'а
над одним use case (спека §3, §12.1).

---

## 3. User Stories

### Оператор платформы

- **US-O1**: Как оператор, я хочу видеть обзор платформы одной командой
  `platform status`, чтобы понять, сколько сервисов работают и сколько
  требуют внимания. *(спека §8.3)*
- **US-O2**: Как оператор, я хочу видеть для каждого наблюдения источник,
  время и свежесть, чтобы отличать «не настроено» от «не удалось проверить». *(§5.2)*
- **US-O3**: Как оператор, я хочу получать в выводе явный следующий шаг
  (`platform service logs api --since 10m`), чтобы не вспоминать команды. *(§4)*
- **US-O4**: Как оператор, я хочу, чтобы CLI не ломал данные при Ctrl-C
  (exit 130, lock освобождён, ничего не изменено), чтобы прерывание было безопасным. *(§5.7)*
- **US-O5**: Как оператор, я хочу журнал мутаций (`кто/когда/что/итог`),
  чтобы отвечать на вопрос «кто задеплоил в 3 ночи». *(§13.5, F18)*
- **US-O7**: Как оператор, я хочу `platform info` с версиями CLI и
  зависимостей, путями и состоянием окружения, чтобы отличать проблему
  окружения CLI от проблемы платформы. *(F14, §7.2)*

### Разработчик сервиса

- **US-D1**: Как разработчик, я хочу создать сервис через мастер
  `platform service create`, чтобы не собирать service.yml и compose руками. *(F5, §13.3)*
- **US-D2**: Как разработчик, я хочу деплоить с пошаговым прогрессом и
  атрибуцией упавшего шага, чтобы сразу видеть, где именно сломалось. *(F3, §9.2)*
- **US-D3**: Как разработчик, я хочу логи с подсветкой уровней и
  `--since/--grep/--container`, чтобы быстро фильтровать шум. *(F4, §9.3)*
- **US-D4**: Как разработчик, я хочу restart с подтверждением, показывающим
  последствия, чтобы случайно не ронять публичный URL. *(§5.5)*
- **US-D5**: Как разработчик, я хочу автодополнение имён сервисов и
  снапшотов, чтобы не помнить их наизусть. *(F9, §14)*
- **US-D6**: Как разработчик, я хочу `platform service start api`, чтобы
  поднять остановленный сервис без полной пересборки. *(F17, §7.3)*

### CI / скрипт / cron

- **US-C1**: Как CI-скрипт, я хочу `--json` на всех командах с
  `schema_version`, чтобы парсить результат без хрупкого разбора текста. *(F10, N8)*
- **US-C2**: Как CI-скрипт, я хочу гарантию «никогда не prompt'ит» в
  non-TTY и под `--no-input`, чтобы пайплайн не зависал. *(§12.5)*
- **US-C3**: Как CI-скрипт, я хочу строгие exit codes (0/1/2/3/4/130),
  чтобы гейтить по типу причины, а не по тексту ошибки. *(§12.4)*
- **US-C4**: Как CI-скрипт, я хочу `diag validate --fail-on` с ignore-list,
  чтобы известные findings не шумели вечно. *(F7, §15.2)*
- **US-C5**: Как cron-скрипт, я хочу заглушки старых плоских команд с
  подсказкой замены, чтобы старые вызовы падали понятно, а не молча. *(F16, §7.5)*

### Backup / восстановление (оператор, CI)

- **US-B1**: Как оператор, я хочу restore снапшота с показом последствий
  (снапшот, целевой сервис, остановка сервиса, семантика перезаписи) и
  безопасной отменой, чтобы не снести живой сервис по ошибке. *(C6, §5.5)*
- **US-B2**: Как оператор, я хочу `backup list` с возрастом и размером
  снапшотов, чтобы выбрать правильный снапшот. *(§7.2)*
- **US-B3**: Как CI, я хочу `restore --no-wait`, чтобы получить job id и не
  блокировать пайплайн. *(§7.4)*

**Story map (критический путь):** status (observe) → diag validate (explain)
→ deploy/restart (act) → status/postcheck (verify). Мастер create — входная
точка для нового сервиса; backup-операции — отдельная ветка жизненного цикла.

---

## 4. Functional Requirements

### 4.1 Feature List

| Feature ID | Название | Спека | Связанные US |
|---|---|---|---|
| F-001 | Группы команд `service/diag/backup/proxy` + `status`/`info` на верхнем уровне | §7.1, F1 | все |
| F-002 | `status` с секциями (services, health, problems по умолчанию) | §8.1, F2 | US-O1 |
| F-003 | `deploy` с пошаговым прогрессом и атрибуцией шага | §9.2, F3 | US-D2 |
| F-004 | `logs` с подсветкой, фильтрами, `--follow`, NDJSON | §9.3, F4 | US-D3 |
| F-005 | `service create` — wizard + полные флаги | §13.3, F5 | US-D1 |
| F-006 | Опциональные аргументы: TTY → интерактив, non-TTY → exit 2 | §5.4, F6 | US-C2 |
| F-007 | `diag validate` — аудит, exit 4, `--json` | §15.2, F7 | US-C4 |
| F-008 | `diag server` по имени или домену | §15.3, F8 | US-O3 |
| F-009 | Autocomplete сервисов (ФС) и снапшотов (кэш) | §14, F9 | US-D5 |
| F-010 | `--json` на всех командах, включая мутации | §12.2, F10 | US-C1 |
| F-011 | `--watch` на status | §8.4, F11 | US-O1 |
| F-012 | Управление контейнерами при недоступном Master | §11.2, F12 | US-O1, US-D2 |
| F-013 | Единый ui-слой (прямой console.print запрещён) | §5.6, F13 | — (качество) |
| F-014 | `info` — единственная сводка окружения и зависимостей | §7.2, F14 | US-O7 |
| F-015 | Секция `problems` — лёгкие read-only проверки | §15.1, F15 | US-O1 |
| F-016 | Заглушки старых команд, exit 2 | §7.5, F16 | US-C5 |
| F-017 | `service start` — подъём без build | §7.3, F17 | US-D6 |
| F-018 | Журнал операций (append-only) | §13.5, F18 | US-O5 |
| F-019 | Backup: create/list/restore/delete через Master API | §7.2, §5.5 | US-B1–B3 |

### 4.2 Non-Functional Requirements

| ID | Требование | Спека |
|---|---|---|
| N-001 | Производительность: status ≤ 2с, completion ≤ 100мс p95, старт ≤ 150мс | §17.1 |
| N-002 | Exit codes 0/1/2/3/4/130 | §12.4 |
| N-003 | `NO_COLOR`/`TERM=dumb`/`--no-color`/non-TTY отключают цвета везде | §12.1 |
| N-004 | Lock-политика: scoped, после prompt'ов, flock | §13.4 |
| N-005 | Python ≥ 3.11, Linux-only | §11.5 |
| N-006 | Секреты не попадают в вывод, включая `--verbose` | §16 |
| N-007 | Внешние процессы argv-массивом, cwd, таймаут | §16 |
| N-008 | `schema_version` в JSON, несовместимые изменения только мажорно | §12.2 |
| N-009 | Языковая политика: машинные поля — EN, человеческий текст — RU | §7.6 |
| N-010 | Параллельный опрос источников с общим deadline | §17.1 |

### 4.3 Feature Dependencies (критическая цепочка)

```
F-001 (каркас/группы)
  ├─ F-013 (ui-слой) ─┬─ F-002 (status) ── F-011 (--watch)
  │                    ├─ F-015 (problems)
  │                    ├─ F-014 (info)
  │                    └─ F-004 (logs)
  ├─ F-006 (интерактивность) ── F-005 (create wizard)
  ├─ F-010 (--json) ── F-003 (deploy) ── F-017 (start/stop/restart)
  ├─ F-007 (diag validate) ── F-008 (diag server)
  └─ F-009 (completion) — зависит от ФС-discovery, не блокируется ничем
F-016 (заглушки) — встраивается в F-001, нужна только до удаления legacy
F-018 (журнал) — подключается к F-003/F-005 и backup-операциям
```

Фазовый план P0–P7 (спека §18.1) согласован: MUST-фичи закрываются к P4,
SHOULD — к P7.

---

## 5. Prioritization (MoSCoW)

### 5.1 Матрица

| Feature ID | Название | Priority | Rationale |
|---|---|---|---|
| F-001…F-007, F-009, F-010, F-012…F-014 | Каркас, status, deploy, logs, create, интерактивность, diag validate, --json, ui-слой, info | **Must Have** | 12/19 (63%); без них CLI не выполняет миссию |
| F-008 | diag server | Should Have | Нужен оператору, но есть bash-оригинал как workaround (§15.3) |
| F-011 | `--watch` | Should Have | Удобство наблюдения; без него status перезапускается вручную |
| F-015 | problems-секция | Should Have | Значительно ускоряет диагноз, но status полезен и без неё на старте |
| F-016 | Заглушки старых команд | Should Have | Защита cron/runbooks; переживает релиз legacy |
| F-017 | `service start` | Should Have | Workaround — полный deploy |
| F-018 | Журнал операций | Should Have | Аудит важен, но не блокирует эксплуатацию |
| F-019 | Backup create/list/restore/delete | Should Have | В MVP входит по фазе P4; прямой доступ к Master API — workaround, но ломает единую точку входа |
| — | resources-секция в status | **Could Have** | Дорогая (docker stats ≥ 1с), вне дефолтного бюджета (§8.1) |
| — | История health («падает N мин») из Master | Could Have | Необязательное обогащение (Q2), не влияет на корректность |
| — | `--install-completion` интеграция в install.sh | Could Have | Установка вручную возможна (§14) |
| Textual dashboard | — | **Won't Have (v1)** | Отложено по решению спеки (§1.2) |
| `service delete`, автофикс/`--fix`, порт diagnose-client.sh, изменение Master Service | — | **Won't Have (v1)** | Явные границы скоупа (§1.3) |

**Валидация пропорций:** Must = 12/19 (63%) — в диапазоне рекомендуемых ~60%,
приемлемо для реорганизации существующего продукта («Must» здесь — parity
функциональности, а не новые рынки). Won't Have = 4 позиции — трейд-оффы
зафиксированы явно. Приоритет MoSCoW ≠ членство в фазе: MVP (P1–P4) содержит
все MUST + SHOULD-фичи по фазам (F-015 в P2; F-011/F-017/F-018/F-019 в P4).

### 5.2 Release Planning

- **MVP (P1–P4):** все Must Have + SHOULD-фичи по фазам → команда `platform2` в бранче `feature/cli-v2`
- **v1.0 (P5–P7):** + Should Have, parity-аудит, wheel/container, переезд
  entry point на `platform`, deprecated-сообщение для `ops`
- **v2.x:** оценка Could Have по реальному опыту эксплуатации

---

## 6. Acceptance Criteria

Формат Given/When/Then. Спека уже содержит сценарии C1–C7 (Приложение C) —
они включены ниже с привязкой к фичам и расширены до полного покрытия.

### F-002 status

- **AC-F002-01 (= C1).** Given Master API недоступен, Docker и ФС доступны /
  When `platform status` / Then exit 0; секции services и problems полные;
  health: `unavailable` с причиной; в выводе «Несобрано: …»; нет traceback.
- **AC-F002-02.** Given сервис без `health.endpoint` в манифесте /
  When `platform status` / Then в секции health строка `health не настроен`
  (не `unknown`, не пропуск строки); exit 0.
- **AC-F002-03 (граница).** Given deadline 2с истёк, секция resources ещё не
  собрана / When `platform status --sections services,resources` /
  Then выведены собранные секции, resources помечена причиной таймаута,
  JSON содержит `complete: false`; exit 0 (без `--strict`).
- **AC-F002-04.** Given `--strict`, секция backups недоступна /
  When `platform status --strict` / Then exit 3, структурная ошибка
  `master_unavailable`.

### F-003 deploy

- **AC-F003-01 (= C2).** Given сломан Dockerfile сервиса api /
  When `platform service deploy api --build` / Then exit 1; последняя строка
  `✘ build`; панель со stderr; `--json` содержит `steps[]` с
  `state: failed` на `build`.
- **AC-F003-02.** Given Master API недоступен, Docker жив /
  When `platform service deploy api` / Then шаг routing помечен warning
  «маршрут может быть не сгенерирован» (не успех); exit 0 при успешном
  postcheck, иначе exit 1.
- **AC-F003-03 (граница).** Given контейнеры поднялись, health не проходит
  30 секунд / When `platform service deploy api` / Then exit 1, сообщение
  «сервис запущен, но не прошёл health; логи: platform service logs api».

### F-004 logs

- **AC-F004-01 (= C3).** Given сервис пишет логи /
  When `platform service logs api --follow --json | head -5` / Then ровно 5
  NDJSON-строк в stdout; никаких заголовков/прогресса в stdout;
  `schema_version` в каждой записи.
- **AC-F004-02.** Given `--grep "Connection refused"` /
  When `platform service logs api --grep 'Connection refused' --since 15m` /
  Then только совпадающие строки, совпадения подсвечены.
- **AC-F004-03 (ошибка ввода).** Given невалидный regex, напр. `--grep '('` /
  When запуск / Then exit 2 с `invalid_value`, подсказка про синтаксис regex.

### F-005 create

- **AC-F005-01 (= C4, non-TTY).** Given non-TTY и полный набор флагов
  (`--name x --visibility public --routing none --container-name x-main
  --no-input`) / When `platform service create` / Then файлы созданы
  атомарно, `service.yml` записан последним; последующий
  `diag validate` — exit 0.
- **AC-F005-02.** Given non-TTY, отсутствует `--routing` /
  When `platform service create ...` / Then exit 2, `arg_missing`, подсказка
  с требуемыми флагами; **ни один файл не создан**.
- **AC-F005-03 (граница имени).** Given имя `Api.v2` (заглавные, точка) /
  When create / Then exit 2, `name_invalid`, правила имени из §13.3.
- **AC-F005-04.** Given TTY, все параметры переданы флагами /
  When `platform service create ...` / Then preview пропущен, запись
  выполнена без подтверждения (`--yes` не требуется).

### F-006 интерактивность / F-010 --json

- **AC-F006-01.** Given TTY, `service restart api`, без `--yes` /
  When запуск / Then подтверждение показывает число перезапускаемых
  контейнеров; явный отказ (N) → exit 0 («операция отменена»), ничего не
  изменено; Ctrl-C → exit 130.
- **AC-F006-02.** Given non-TTY, мутация без `--yes` /
  When запуск / Then exit 2 (`no_tty`), операция **не выполняется**.
- **AC-F010-01.** Given любая команда с `--json` /
  When запуск / Then stdout содержит только один JSON-объект с
  `schema_version`; человекоориентированные сообщения — в stderr.

### F-007 diag validate

- **AC-F007-01 (= C5).** Given один finding подавлен ignore-list, второй
  error существует / When `platform diag validate --json --fail-on error` /
  Then exit 4; новый finding в `findings[]`; подавленный —
  `suppressed: true`, не входит в `summary.errors`.
- **AC-F007-02.** Given только warnings, `--fail-on error` (дефолт) /
  When validate / Then exit 0; при `--fail-on warning` — exit 4.
- **AC-F007-03 (граница).** Given Docker недоступен /
  When validate / Then exit 4, если error-findings из статических проверок;
  runtime/network-проверки пропущены с note «Docker недоступен —
  runtime не проверен» (не маскируются под успех).

### F-012 деградация / F-016 заглушки / F-014 info

- **AC-F012-01.** Given Master недоступен, Docker жив /
  When `platform service restart api --yes` / Then операция выполняется,
  exit 0; никаких routing-замечаний (restart не трогает роутинг —
  routing-warning только у deploy, AC-F003-02).
- **AC-F016-01 (= C7).** When `platform deploy api` / Then stdout пуст,
  stderr содержит «Стало: platform service deploy api», exit 2.
- **AC-F014-01.** Given несовместимость версий CLI и Master /
  When `platform info` / Then отчёт с версиями обеих сторон и пометкой
  несовместимости; **exit 0** (info — отчёт, матрица спеки §11.2). Exit 3
  `master_incompatible` — только для команд, требующих Master (`backup *`);
  никогда traceback.

### F-008 diag server / F-011 watch / F-017 start / F-018 журнал / F-009 completion

- **AC-F008-01.** Given домен `help.openedu.urfu.ru`, манифест сервиса
  `support` (имя ≠ метка домена) / When `platform diag server
  help.openedu.urfu.ru` / Then манифест резолвится через `routing[]`,
  отчёт по этапам, exit по `--fail-on`.
- **AC-F011-01.** Given `--watch 1` / When два тика подряд /
  Then каждый тик — отдельный NDJSON-снимок с `seq`; второй тик не стартует,
  пока идёт сборка первого; Ctrl-C → exit 130 без traceback.
- **AC-F017-01.** Given остановленный сервис / When
  `platform service start api` / Then `compose up -d` **без build**;
  сервис поднят; exit 0; подтверждение не запрашивается (§5.5).
- **AC-F018-01.** Given выполнен `service restart api` /
  When чтение `<project>/.platform-journal.log` / Then запись содержит
  время, uid, команду, объект, результат, длительность; файл дописывается,
  не перезаписывается.
- **AC-F009-01 (бюджет).** Given 10 сервисов, кэш снапшотов свежий /
  When completion по `<TAB>` после `platform service logs` /
  Then p95 ≤ 100мс, только scandir ФС, без docker/сети.

### F-019 backup

- **AC-F019-01 (= C6).** Given снапшот S сервиса api, целевой сервис api
  запущен / When `platform backup restore S --target api` в TTY, Ctrl-C на
  подтверждении / Then exit 130; сервис не остановлен; ничего не записано;
  повторный запуск показывает те же последствия (снапшот, цель, остановка,
  перезапись).
- **AC-F019-02.** Given restore без `--force`, целевые данные конфликтуют /
  When запуск / Then exit 2 `restore_conflict` с отчётом о конфликте; ничего
  не перезаписано.
- **AC-F019-03.** Given Master недоступен / When `platform backup list api` /
  Then exit 3 `master_unavailable` (матрица §11.2 спеки).
- **AC-F019-04.** Given `restore ... --no-wait` / When запуск / Then
  немедленный ответ с job id; журнал операций (§13.5) фиксирует запуск.

---

## 7. Assumptions & Constraints

### 7.1 Assumptions (допущения PRD-слоя — в спеке не зафиксированы)

1. Success-метрики из §1.2 — предложение, требуют утверждения командой.
2. «Пропорция Must ≈ 78%» приемлема, т.к. это реорганизация существующего
   продукта, а не новый продукт.
3. Backup-операции вынесены в US-B1–B3 и фичу F-019 (Should Have, фаза P4);
   зависимость от Master API — обязательная (матрица §11.2 спеки).
4. Пользователи CLI — русскоязычные операторы (человеческий текст RU, §7.6).

### 7.2 Constraints

- Технические: Python ≥ 3.11, Linux-only, Docker ≥ 20.10, docker.sock (§11.5)
- Архитектурные: зависимости только в сторону домена; тесты подменяют
  порты, не helper'ы CLI (§10.2); мутации из контейнера запрещены
  структурно (`environment_mismatch`, §11.5)
- Процессные: ruff/black — процесс, не продукт (N5); фазы P0–P7 с
  критериями выхода (§18.1)

### 7.3 Risks

| Риск | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Q9 (общий lock-каталог с Master) не решён к P3 — конфликт операций | High | Medium | Журнал операций + postcheck; lock-тесты в P3 (§13.4) |
| Q6 (стратегия health-пробы) — ложные «failing» на порт-сервисах | Medium | Medium | TCP-connect fallback; `not_applicable` статус; порог `probe_min_interval` (§17.2) |
| Деградационная матрица сложна — риск «молчаливой» частичности | Medium | Low | Матрица §11.2 как чек-лист тестов P2; `complete: false` в JSON |
| Golden-тесты ширины 60/80/120 не покрывают реальные терминалы | Low | Medium | Дополнить ручной проверкой в P7 smoke (§18.2) |
| Снапшот-кэш completion рассинхронизируется между операторами | Low | Low | TTL 30с, stale fallback, atomic write, project identity (§14) |

---

## 8. Open Questions (после решений оператора 2026-10-06, срез спеки §19)

- [x] **Q4** — закрыт: bash-скрипт как wheel-asset + тонкая обёртка (спека §15.3)
- [x] **Q6** — закрыт: container IP + internal_port (primary), published port
  (fallback), TCP для порт-сервисов
- [x] **Q9** — закрыт: `.platform-locks/` в корне проекта; Master не
  координируется в v1; контейнерный режим — read-only
- [ ] **Q2** — неблокирующее: дополнение Master API endpoint'ом
  health-snapshot (схема — заглушка спеки §11.6.4)
- [ ] **Q3** — неблокирующее: deployments metadata в Master API; журнал
  операций (§13.5) — минимум

---

## Appendix A. Соответствие техдизайну

| PRD-раздел | Источник в спеке |
|---|---|
| §1 Background/Scope | §1.1–§1.3 |
| §2 Personas | §3 |
| §3 User Stories | §4 (цикл), §6.1 (F1–F18), §5 (принципы) |
| §4 Requirements | §6.1, §6.2 |
| §5 MoSCoW | §6.1 (MVP-срез), §1.3 (out of scope), §8.1 (resources) |
| §6 Acceptance Criteria | Приложение C (C1–C7) + расширения |
| §7.3 Risks | §13.4, §17.2, §19 (Q6, Q9), §18.2 |
| §8 Open Questions | §19 |
