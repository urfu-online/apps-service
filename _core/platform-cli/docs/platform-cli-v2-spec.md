# Platform CLI v2: сводный дизайн-документ

> Версия: 1.2 — итоговое ТЗ, **УТВЕРЖДЕНО оператором 2026-10-06**
> Дата: 2026-10-06
> Статус: единственный авторитетный документ для бранча `feature/cli-v2`.
> Источники: [`redesign-v2.md`](redesign-v2.md) (техдизайн),
> [`platform-cli-product-design.md`](platform-cli-product-design.md) (продуктовая концепция),
> [`platform-cli-v2-PRD.md`](platform-cli-v2-PRD.md) (влит в Приложения G/H),
> внешний ревью, производственная база 2026-10-06 (Приложение F).
> Журнал слияния и решений — Приложение A.

Правило чтения: каждое правило имеет **один** раздел-владелец; §6.2 — только
индекс со ссылками. Ревизия 1.1 сделана по внешнему ревью: устранены следы
слияния, добавлены матрица деградации (§11.2), реестр кодов ошибок (§12.4),
сводная таблица опций (§7.4), контракт манифеста (Приложение B), приёмочные
сценарии (Приложение C), пересобраны фазы (§18).

Ревизия 1.2: решения оператора зафиксированы (Q9=(a), Q4=(a), утверждение
спеки — Прил. A14–A17), дополнения Master API разрешены (§1.3, §11.6.4),
добавлена производственная база среза 2026-10-06 (§11.6, Прил. F), PRD влит
(Прил. G, H) и больше не редактируется — этот документ стал итоговым ТЗ.

---

## Содержание

1. [Цель и контекст](#1-цель-и-контекст)
2. [Видение](#2-видение)
3. [Пользователи](#3-пользователи)
4. [Модель опыта](#4-модель-опыта)
5. [Принципы](#5-принципы)
6. [Требования](#6-требования)
7. [Командный интерфейс](#7-командный-интерфейс)
8. [Status как центральный сценарий](#8-status-как-центральный-сценарий)
9. [Экраны и примеры вывода](#9-экраны-и-примеры-вывода)
10. [Архитектура](#10-архитектура)
11. [Источники данных, деградация и среда](#11-источники-данных-деградация-и-среда)
12. [Контракты CLI](#12-контракты-cli)
13. [Интерактив, подтверждения, мастера и locks](#13-интерактив-подтверждения-мастера-и-locks)
14. [Completion](#14-completion)
15. [Диагностика](#15-диагностика)
16. [Безопасность](#16-безопасность)
17. [Производительность](#17-производительность)
18. [План работ и тестовая стратегия](#18-план-работ-и-тестовая-стратегия)
19. [Открытые вопросы](#19-открытые-вопросы)
20. [Приложения](#20-приложения)

---

## 1. Цель и контекст

### 1.1 Проблема

Текущий platform CLI решает задачи, но с точки зрения опыта оператора это
«10 разных скриптов, собранных в один бинарник»:

- Вывод вразнобой: каждый модуль печатает по-своему (`✅`, `❌`, `ℹ️`, сырые
  строки docker), нет единого визуального языка.
- Нет интерактивности: имя сервиса нужно помнить и набирать; ошибки аргументов —
  единственная обратная связь.
- Нет автодополнения: Typer создаётся с `add_completion=False` (см.
  `apps_platform/cli.py`, создание `app`), имена сервисов не подставляются.
- Диагностика живёт отдельно от CLI: `scripts/validate.py` (216 строк, свой
  root-resolution и вывод), `docs/diagnostics/diagnose-server.sh` (618 строк
  bash), `diagnose-client.sh` (237), `diagnose-all.sh` (122). Оператор ползает
  по истории терминала, вспоминая, что и как запускать.
- Команды `list`/`status`/`logs` показывают часть картины: нет health-сводки,
  ресурсов, бэкапов, «что сейчас не так».

### 1.2 Решение

Перестроить CLI в отдельном бранче `feature/cli-v2`: **CLI-слой, вывод и структура
пакета переписываются, проверенная доменная логика переиспользуется** (§10.5).
Это реорганизация с заменой каркаса, а не «с нуля с сохранением» — каркас новый,
домен старый. Ключевые решения (зафиксированы интервью):

- CLI — **единая точка входа** для всего: управление, диагностика, бэкапы,
  обслуживание. Пользователь не должен знать о скриптах вне CLI.
- Два режима равнозначны: **человек за терминалом** (интерактив по умолчанию)
  и **скрипты/CI** (`--json`, `--no-input`, строгие exit codes).
- Командная поверхность **переразбивается по объектам**; старые плоские команды
  не сохраняются, но получают **заглушки-подсказки** (§7.5) — cron и runbooks
  не ломаются молча.
- Дашборд (Textual) — вне спеки; возможно позже отдельным документом по
  реальному опыту использования. Не блокирует ни одну фазу.

### 1.3 Границы скоупа

**В скоупе:**

- Перестройка пакета `apps_platform`: структура, слой вывода, каркас команд.
- Перенос `scripts/validate.py`; порт `diagnose-server.sh`; судьба
  `diagnose-client.sh`/`diagnose-all.sh` — решение в §15.4.
- Соглашения JSON/NDJSON, exit codes, lock-политика, completion.
- Визуальная система вывода, интерактивные мастера и выборы.
- Минимальные дополнения Master Service API — только как **необязательное
  обогащение** (§19, Q2); ничего блокирующего.

**Вне скоупа v1:**

- Master Service: интерфейс остаётся совместимым, но **дополнения и
  переписывание отдельных его endpoints разрешены** (решение оператора
  2026-10-06: «если для CLI понадобится переписать Master API — значит так»;
  Прил. A16). Кандидаты — заглушки §11.6.4; конкретные роуты/схемы — на этапе
  ТЗ Master, CLI не блокируется.
- Миграция `ops` bash-обёртки: deprecated-сообщение с заменой (§18.1, P7).
- **Автофикс конфигурации**: CLI никогда не меняет файлы/конфиги/контейнеры по
  собственной инициативе. Валидатор выводит fix-команды как **текст для
  копирования**; никакого `--fix` в v1 (§5.8, §15.2).
- **Удаление сервиса** (`service delete/rm`): трогает тома, реестр манифестов и
  caddy-конфиги; ручная операция. Вынесено явно, не открытый вопрос.
- Textual dashboard — вне спеки (§1.2).

---

## 2. Видение

Platform CLI — не набор команд над Docker и Master API, а **операторская консоль
платформы**. Цикл: `увидеть состояние → понять причину → безопасно изменить →
проверить результат`. Три свойства:

- **Правдивость.** CLI показывает источник и свежесть сведений, отличает
  «не настроено» от «не удалось проверить» и не выдаёт предположение за факт.
- **Управляемость.** Сервисами можно управлять напрямую через Docker/Compose,
  даже если Master API недоступен.
- **Предсказуемость.** Один и тот же ввод имеет понятный результат в терминале,
  CI и скрипте; вопросы и подтверждения никогда не возникают неожиданно.

Если для ответа нужно знать внутренний helper, угадывать источник значения,
парсить нестабильный текстовый вывод или листать историю терминала — CLI
миссию не выполнил. Измеримая приёмка — Приложение C.

---

## 3. Пользователи

| Пользователь | Основная задача | Хороший результат |
|---|---|---|
| Оператор платформы | Понять, что работает и что сломано | Один обзор с явной свежестью данных и следующим шагом |
| Разработчик сервиса | Создать, задеплоить, проверить, изучить логи | Короткий повторяемый цикл без знания Master API |
| CI / скрипт / cron | Запустить операцию и надёжно определить результат | JSON-контракт, exit codes, отсутствие prompt'ов |

Все три лица используют **одни и те же сценарии приложения и модели данных** —
два presenter'а над одним use case (§12.1), не две реализации.

---

## 4. Модель опыта

Цикл из четырёх фаз; команды поддерживают его целиком — не требуют помнить
предыдущий вывод, внутренние имена или порядок флагов из прошлой сессии.

1. **Observe** — сводка: `platform status`.
2. **Explain** — почему неизвестно/проблемно, откуда сведения, когда получены,
   что проверить дальше.
3. **Act** — явная операция над конкретным сервисом/снапшотом.
4. **Verify** — результат операции и независимая проверка нового состояния.

Типовая сессия:

```text
$ platform status
Платформа: 8 из 9 сервисов работают, 1 требует внимания      [fs+docker+caddy, 1.4s]

  api      public    ● running   health ✘ failing   8s назад
  web      public    ● running   health ✔ ok        12s назад
  ...

Problems (2)
  ✘ legacy: visibility=public, но сервис лежит в services/internal/
  ✘ api: контейнер 'api-web' не в platform_network

Следующий шаг: platform service logs api --since 10m

$ platform service logs api --since 10m
...

$ platform service restart api
Перезапустить api? Будут перезапущены 2 контейнера. [y/N]: y
✔ перезапущен за 3.8s

$ platform status api
api: ● running, health ✔ ok, проверено только что
```

Предложенные в выводе команды — **подсказка, а не действие**: CLI никогда сам
не выполняет следующий шаг.

---

## 5. Принципы

### 5.1 Сначала состояние, затем управление

- `platform status` без аргументов — обзор платформы; никогда не prompt'ит.
- `platform status <service>` — состояние одного сервиса.
- Мутации требуют явной цели (сервис, снапшот).

### 5.2 Не скрывать неопределённость

Каждое наблюдение несёт: **состояние, источник, время наблюдения, свежесть**.
`unknown` не универсальная отписка, причина различается явно (§20, Приложение D):

- `health не настроен` — факт конфигурации (нет `health.endpoint` в манифесте);
- `Master API недоступен` — деградация источника;
- `проверено 3 мин назад` — устаревание;
- `Docker Engine недоступен` — нет обязательной зависимости.

### 5.3 Один сценарий, два интерфейса

Текстовый и JSON-рендереры получают один типизированный результат use case.
JSON не собирается из текста; human output не парсится скриптами.

### 5.4 Вопросы только по делу

- Prompt — только для отсутствующих обязательных значений и только в TTY
  (§13.2). `--no-input` запрещает все вопросы; нехватка ввода → exit 2 +
  подсказка.
- `--yes` пропускает **только подтверждения**; не выбирает сервис и не
  подменяет параметры операции (`--target`, `--force`).
- Исключение: `status` без аргументов — сценарий просмотра, не prompt.

### 5.5 Подтверждение показывает последствия

Перед изменением CLI показывает объект, действие, последствия:

| Операция | Подтверждение | Показывает |
|---|---|---|
| `service stop` | да | URL сервиса, который перестанет отвечать |
| `service restart` | да | число перезапускаемых контейнеров |
| `service start` | нет | — |
| `service deploy` | **нет** | не деструктивная операция поверх существующего сервиса; `--yes` в реестре отсутствует |
| `service create` | preview в TTY; пропускается, если все параметры даны флагами | сгенерированные файлы |
| `backup restore` | да | снапшот, целевой сервис, семантика перезаписи, остановка сервиса |
| `backup delete` | да | необратимое удаление снапшота |

`--yes` пропускает диалог, но не заменяет параметры (`--target`, `--force`).

### 5.6 Вывод без декоративного обязательства

- Единый ui-слой обязателен (F13): все цвета/таблицы/статусы только через него.
  При этом универсальная рамка — не самоцель: применяются компоненты, которые
  повышают читаемость.
- Логи построчные; узкий терминал → компактное представление, а не обрезанные
  колонки.
- Важный статус дублируется текстом; цвет — не единственный носитель смысла.

### 5.7 Прогресс и отмена

Длительная операция сразу сообщает о начале, показывает этап, корректно
реагирует на Ctrl-C: останавливает дочерний процесс, не оставляет lock, не
утверждает успех, exit 130 без traceback.

### 5.8 Правдивость важнее красоты

- Не показывать то, чего не знаем: нет авторитетного источника — нет поля
  («последний деплой/версия», §11.4).
- Кэш — оптимизация скорости, не источник правды; кэшированные данные
  маркируются возрастом.
- Никакого автофикса (§1.3); диагностика только предлагает команды текстом.
- Подсветка уровней логов — по распознанным маркерам (`ERROR`, `WARN`,
  `WARNING`, `CRITICAL`, `FATAL`); эвристика задокументирована в help, для
  машинного разбора есть `--json`.

---

## 6. Требования

### 6.1 Функциональные (с приоритетами)

| # | Приор. | Требование |
|---|---|---|
| F1 | MUST | Группы `service`, `diag`, `backup`, `proxy`; `status` и `info` на верхнем уровне (Прил. A, A1/A3) |
| F2 | MUST | `status` — секции; дефолт `services, health, problems`; конфиг + `--sections` |
| F3 | MUST | `deploy` — пошаговый прогресс с таймингами и атрибуцией упавшего шага |
| F4 | MUST | `logs` — подсветка, `--since`/`--grep` (regex, фильтр+подсветка), `--json`, `--follow`, `--container` |
| F5 | MUST | `service create` — wizard при нехватке аргументов; полные флаги → молча |
| F6 | MUST | Опциональные аргументы: нет значения в TTY → интерактивный выбор; non-TTY без значения → exit 2 |
| F7 | MUST | `diag validate` — аудит; exit 4 при error-findings; `--json` |
| F8 | SHOULD | `diag server TARGET` — по имени ИЛИ домену (§15.3) |
| F9 | MUST | Autocomplete сервисов (из ФС) и снапшотов (кэш Master) |
| F10 | MUST | `--json` на **всех** командах, включая мутации: результат содержит шаги, длительности, id (снапшоты) |
| F11 | SHOULD | `--watch` на status (§8.4) |
| F12 | MUST | Управление контейнерами работает при недоступном Master (исключение — `backup`, §11.2) |
| F13 | MUST | Единый ui-слой: прямой `console.print` в командах запрещён |
| F14 | MUST | `info` — версия CLI, project root, пути, версии/доступность зависимостей (единственное место с этой сводкой) |
| F15 | SHOULD | Секция `problems` — лёгкие read-only проверки без фиксов |
| F16 | SHOULD | Заглушки старых команд с подсказкой замены, exit 2 (§7.5) |
| F17 | SHOULD | `service start` — подъём остановленного сервиса без build (§7.3) |
| F18 | SHOULD | Журнал операций: append-only лог мутаций (кто/когда/что/итог) (§13.5) |

MUST-набор: F1–F7, F9, F10, F12–F14. MVP (P1–P4) = все MUST + SHOULD-фичи
по фазам (F15 в P2, F16 в P1, F11/F17/F18 в P4): приоритет MoSCoW и членство
в фазе — независимые вещи. Остальное SHOULD — фазы P5–P7.

### 6.2 Нефункциональные требования — индекс

| # | Требование | Владелец |
|---|---|---|
| N1 | Бюджеты производительности: status ≤ 2с (настраиваемо), completion ≤ 100мс p95, старт CLI ≤ 150мс | §17 |
| N2 | Exit codes 0/1/2/3/4/130 | §12.4 |
| N3 | `NO_COLOR`/`TERM=dumb`/`--no-color`/non-TTY отключают цвета и анимацию везде | §12.1 |
| N4 | Lock-политика (scoped, после prompt'ов, flock) | §13.4 |
| N5 | Python ≥ 3.11; Linux-only среда (§11.5); ruff/black — процесс, не продукт (CONTRIBUTING) | §11.5 |
| N6 | Секреты не попадают в вывод, включая `--verbose` | §16 |
| N7 | Внешние процессы argv-массивом, cwd, бюджет времени | §16 |
| N8 | JSON-схемы версионируются (`schema_version`), не меняются несовместимо в минорных версиях | §12.2 |
| N9 | Языковая политика вывода | §7.6 |
| N10 | Параллельный опрос источников | §17.1 |

---

## 7. Командный интерфейс

### 7.1 Грамматика

```text
platform <группа> <команда> [позиционные] [опции]
platform status [SERVICE]      # исключение: cross-resource обзор на верхнем уровне
platform info
```

Группы: `service`, `diag`, `backup`, `proxy`. Позиционные аргументы целевых
объектов (сервис, снапшот) везде опциональны по семантике §5.4, кроме мест,
где цель — часть команды (`backup restore SNAPSHOT`).

### 7.2 Реестр команд (v1/скрипты → v2)

| v2 | Было | Заметки |
|---|---|---|
| `platform status [SERVICE]` | `status` | живой обзор; никогда не prompt'ит |
| `platform info` | `info` | единственная сводка окружения/зависимостей |
| `platform service list` | `list` | **офлайн-каталог по манифестам** без Docker: имя, visibility, роутинг, URL из манифеста; быстрый, основа completion; `--json` |
| `platform service create [NAME]` | `new` | wizard/флаги (§13.3) |
| `platform service deploy SERVICE` | `deploy` | `--build --pull --dry-run --quiet`; без подтверждения (§5.5) |
| `platform service stop SERVICE` | `stop` | подтверждение с последствиями |
| `platform service start SERVICE` | — (только полный deploy) | подъём без build: `compose up -d` |
| `platform service restart SERVICE` | `restart` | подтверждение; семантика — `docker compose restart` (§13.6) |
| `platform service logs SERVICE` | `logs` | фильтры, подсветка, `--container` |
| `platform diag validate [SERVICE...]` | `scripts/validate.py` | фильтры `--check/--level`, `--fail-on`, ignore-list |
| `platform diag server TARGET` | `diagnose-server.sh` | имя или домен |
| `platform backup create SERVICE` | `backup <svc>` | Master API |
| `platform backup list SERVICE` | — | снапшоты: id, возраст, размер |
| `platform backup restore SNAPSHOT --target SERVICE` | — | явные `--target`/`--force` |
| `platform backup delete SNAPSHOT` | — | необратимо |
| `platform proxy reload` | `reload` | `--container NAME` |

### 7.3 Команды без пары

- `service delete` — вне скоупа (§1.3).
- Остановка без удаления — `service stop`; повторный подъём — `service start`.

### 7.4 Сводная таблица опций (команда × опции)

Общие (все команды): `--verbose`, `--json`, `--no-input`, `--yes`, `--no-color`,
`--project-dir PATH`. Специфичные:

| Команда | Опции | Определение |
|---|---|---|
| `status` | `--sections LIST`, `--watch [N]`, `--strict` | §8; `--watch N` — интервал таблицы в секундах (дефолт 1); `--strict` — недоступность секции → exit 3 |
| `service list` | `--visibility {public,internal,core}` | офлайн-каталог (§7.2) |
| `service create` | `--name --visibility --routing {domain,subfolder,port,none} --domain --path --port --container-name --internal-port --health-endpoint --backup {on,off} --dry-run` | §13.3; `--dry-run` — печатает генерируемые файлы, не пишет |
| `service deploy` | `--build`, `--pull`, `--dry-run`, `--quiet` | `--quiet` — подавляет сырой вывод compose под шагами; без подтверждения |
| `service stop/start/restart` | — | `--yes` из общих опций пропускает подтверждение |
| `service logs` | `--lines N`, `--follow`, `--since WHEN`, `--grep RE`, `--container NAME` | `--grep` — Python-regex: фильтр + подсветка совпадений; невалидный regex → exit 2 |
| `diag validate` | `--check ID...`, `--level {error,warning,note}...`, `--fail-on {error,warning,none}`, `--ignore-file PATH` | §15.2; `--fail-on` дефолт `error` |
| `diag server` | `--json` | TARGET = имя сервиса или домен |
| `backup create/list` | — | — |
| `backup restore` | `--target SERVICE`, `--force`, `--no-wait` | `--force` — перезаписать целевые данные при конфликте (без force конфликт → exit 2 + отчёт); `--no-wait` — вернуть job id, не ждать завершения |
| `backup delete` | — | необратимо; подтверждение |
| `proxy reload` | `--container NAME` | дефолт `caddy` |

Общие опции работают **в любой позиции** (`platform status --verbose` —
валидно): CLI-adapter собирает их до и после подкоманды (ограничение Click
обходится явно).

### 7.5 Заглушки старых команд

Скрытые команды-заглушки (`deploy`, `stop`, `restart`, `logs`, `backup`, `new`,
`list`, `reload`, `status`-дубль) не регистрируются в help, но перехватывают
старые плоские вызовы:

```text
$ platform deploy api
✘ Команда изменена в platform v2.
  Было:     platform deploy api
  Стало:    platform service deploy api
  Подсказка: platform --help; заглушки будут удалены в v2.1
exit 2
```

Заглушки существуют весь v2.x; удаление — только с мажорной версией. Это
закрывает Q5 (deprecated-период для старых команд) дёшево и без ломания cron.

### 7.6 Языковая политика вывода

- **Машинные поля** (`code`, `check`, `state`, уровни) — английские, стабильные
  значения из закрытых реестров.
- **Человеческий текст** — русский (язык существующей кодовой базы и примеров).
- **Длительности** — человеко-формат (`1.4s`, `31.2s`, `8s назад`); в JSON —
  ISO-8601 UTC timestamps + секунды числом.
- Флаги и значения опций — английские.

---

## 8. Status как центральный сценарий

### 8.1 Секции

| Секция | Источники | Содержимое | Стоимость (бюджет) |
|---|---|---|---|
| `services` | fs discovery + docker + caddy | сервис, VIS, статус-маркер, маршрут/URL | дешёвая (данные уже собраны) |
| `health` | прямая проба (основная) + кэш Master (обогащение) | результат, источник, возраст, история («падает 12 мин») | средняя (§19, Q6) |
| `problems` | лёгкие проверки (§15.1) | findings уровня error/warning с следующим шагом | дешёвая (§15.1) |
| `resources` | docker stats + системные | память, диск, размер логов | **дорогая** (`docker stats` ≥1с) — вне дефолтного бюджета, только по запросу |
| `backups` | Master API | последний снапшот + возраст | дешёвая (один API-запрос) |

Дефолт: `services, health, problems`. Секции, которые не удалось загрузить,
выводятся с причиной, а не пропускаются молча.

### 8.2 Конфигурация

```yaml
# ${XDG_CONFIG_HOME:-~/.config}/platform/config.yml  — только preferences
status:
  sections: [services, health, problems]
  compact: false
  deadline: 2s            # общий бюджет сбора секций; при инциденте поднимается
health:
  stale_after: 90s        # порог свежести кэша Master (§11.3)
```

- Неизвестная секция в конфиге → warning; в `--sections` CLI → exit 2 (опечатка
  в командной строке должна падать, в конфиге — терпимо).
- Конфиг не дублирует `.ops-config.yml` и не является source of truth.

### 8.3 Частичность, свежесть, «требует внимания»

- Каждая секция — `SectionResult` (§10.4): state, данные, наблюдения по каждому
  источнику (§11.3), findings.
- Общий status бывает частичным: доступные секции показываются, недоступные —
  с причиной. JSON содержит `complete: false` и причины.
- **Политика exit**: по умолчанию частичный status → exit 0 (с явно описанным
  partial). Для cron/CI: `--strict` (недоступность секции → exit 3) и/или
  `--json` + проверка `complete`. Findings не влияют на exit status'а — для
  гейта есть `diag validate --fail-on` (§12.4).
- **Формула «требует внимания»** (для шапки): сервис считается требующим
  внимания, если health = failing, статус контейнера ∈ {exited, unhealthy,
  crash-loop} или в `problems` есть error-finding по этому сервису. Шапка:
  `N из M сервисов работают, K требуют внимания`.

### 8.4 `--watch [N]`

- `N` — интервал обновления **таблицы** в секундах (дефолт 1; конфиг
  `watch.interval` для изменения дефолта). Нижняя граница прямых health-проб —
  отдельный порог `watch.probe_min_interval` (30с, §17.2): проба чаще него не
  запускается, между пробами показывается последний результат с возрастом.
- Снимок NDJSON — **на каждый завершённый тик** (`seq`, `changed: bool`);
  перекрывающиеся тики пропускаются (сборка дольше интервала → следующий тик
  стартует по завершении).
- Ctrl-C → exit 130 без traceback. Интервал и порог видны в первой строке
  вывода и в help.

---

## 9. Экраны и примеры вывода

Все примеры согласованы с моделью статусов (Приложение D) и языковой политикой
(§7.6). Заголовок сводки везде в формате `[<источники>, <Ns>]`.

### 9.1 `platform status` (дефолтные секции)

```text
Платформа: 8 из 9 сервисов работают, 2 требуют внимания   [fs+docker+caddy, 1.4s]

  SERVICE     VIS       STATUS         ROUTING / URL
  api         public    ● running      https://api.example.test
  web         public    ● running      https://example.test/web
  imap-proxy  internal  ● running      (порт-сервис, HTTP-роутинга нет)
  legacy      public    ○ exited       https://legacy.example.test

Health (прямая проба, кэш Master; проверено 8s назад)
  api      ✘ failing   падает 12 мин (master)  → platform service logs api --since 10m
  web      ✔ ok
  (imap-proxy: health не настроен)

Problems (2)
  ✘ legacy: visibility=public, но сервис лежит в services/internal/
  ✘ api: контейнер 'api-web' не в platform_network (сети: default)

Несобрано: backups (Master API недоступен)
Сводка: 2 проблемы у 2 сервисов → platform diag validate
```

### 9.2 `platform service deploy api --build`

```text
→ preflight   ✔  манифест найден, lock получен
→ build       ✔  28.1s
→ pull        –  пропущен (--pull не задан)
→ up          ✔
→ routing     ●  маршрут в conf.d найден
→ postcheck   ●  health: 2/2 ok (прямая проба)
✔ задеплоен за 31.2s
```

- Шаги: `preflight` (манифест, lock) → `build` (если `--build`) → `pull` (если
  `--pull`) → `up` → `routing` (маршрут присутствует в `conf.d/*.caddy`; если
  Master недоступен и маршрут не сгенерирован — **warning**, не успех-в-квоте:
  «маршрут не сгенерирован, Master API недоступен») → `postcheck` (прямая
  health-проба, **свежий** результат; старая запись кэша не считается
  доказательством).
- Сырой вывод compose показывается под текущим шагом; `--quiet` подавляет.
- Падение шага: красная строка с именем шага, stderr в панели, exit 1.
- `--dry-run` печатает план шагов; non-TTY — построчный лог.
- Postcheck: ожидание healthy до 30с (проверка каждые 2с), затем exit 1 с
  состоянием сервиса в выводе (контейнеры подняты, health failing → «сервис
  запущен, но не прошёл health; логи: platform service logs api»).

### 9.3 `platform service logs api --since 15m`

```text
── api · контейнер svc-web-1 · последние 15м ──
2026-10-06 12:03:41  INFO  запрос обработан
2026-10-06 12:04:02  WARN  соединение к Master: retry 1/3
2026-10-06 12:04:05  ERROR RedisConnectionError: Connection refused
```

- Подсветка: ERROR/CRITICAL/FATAL — красным, WARN/WARNING — жёлтым,
  timestamps — dim; распознанные маркеры — см. §5.8.
- Счётчик «N ERROR, M WARN» в заголовке — **только в ограниченном режиме**
  (без `--follow`, вывод читается до печати). В `--follow` заголовок без счётчиков.
- Мультиконтейнерный сервис: по умолчанию все контейнеры с префиксом имени;
  `--container NAME` выбирает один; префикс всегда виден.
- `--grep` — Python-regex: фильтр строк + подсветка совпадений; `--follow
  --json` — NDJSON по строке; `--json` без follow — массив записей.

### 9.4 `platform diag validate`

```text
Аудит сервисов (services/public, services/internal)

  legacy      ✘ [manifest/visibility-dir] visibility=public, но лежит в services/internal/
              fix: переместить каталог в services/public/
                   или: изменить visibility в service.yml на internal
                   # оба варианта корректны; mv запущенного сервиса — риск,
                   # выбирайте осознанно
  imap-proxy  –  [manifest/routing] routing: none — порт-сервис, норма
  api         ✘ [network/membership] контейнер 'api-web' не в platform_network
              fix (корневая причина): добавить в docker-compose.yml сервиса:
                   networks: platform_network: external: true
                   services.<svc>.networks: [platform_network]
                   # docker network connect — временное средство, не переживёт
                   # пересоздание контейнера

Итого: 2 ошибки, 0 предупреждений, 1 замечание
```

- `fix` — структурированная подсказка (`FixSuggestion`, §10.4): описание,
  команды argv-массивами, указание корневой причины; выводится текстом с
  префиксом `$`/комментариями, никогда не исполняется. Пути в fix-командах
  формируются от текущего project root (абсолютные или с явной привязкой).
- `[check-id]` в каждой строке — для `--check`-фильтрации и ignore-list.
- `--json` — `ValidationReport` (§10.4, Приложение C.4).

---

## 10. Архитектура

### 10.1 Слои и направление зависимостей

Зависимости идут **в сторону домена** (стрелки = «зависит от»):

```text
        CLI adapter (Typer: args, help, exit mapping)      Presenters (text/json/ndjson)
                    \                                          /
                     v                                        /
              Application use cases ─────────────────────────
              (status, deploy, diag, backup: координация,
               deadlines, lock, типизированные результаты)
                              |
                              v
        +----------------------------+      реализуют
        | Domain                     |     (dependency
        | модели, чистые правила,    |<───── inversion)
        | классификация результатов  |            ^
        +----------------------------+            |
                              ^            +-------------+
                              |            | Ports       |
                              |            | (интерфейсы)|
                              |            +-------------+
                              |                   ^
                              |            +------+------+
                              +────────────| Adapters    |
                                           | fs, Compose,|
                                           | Docker,     |
                                           | Caddy, Master|
                                           +-------------+
```

- CLI adapter и Presenters — соседние внешние слои; оба зависят от use cases
  (Presenters получают результат use case), но не друг от друга напрямую.
- Adapters **реализуют** порты; зависимость адаптера направлена к порту/домену.
- Use cases зависят от домена и портов; домен не зависит ни от чего внешнего.

### 10.2 Правила зависимостей

- **CLI adapter** разбирает ввод, вызывает use case, маппит ошибки в exit codes
  (§12.4). Бизнес-правил нет, к Docker/API не обращается.
- **Use cases** координируют источники, deadlines, lock, результат; возвращают
  типизированный результат, а не строки.
- **Domain** — модели и чистые правила; не импортирует Typer, Rich, Docker SDK,
  HTTP-клиент, файловый слой и не запускает процессы.
- **Ports** — только там, где есть разные адаптеры, независимая деградация или
  тестовая подмена. Никаких DI-framework и универсального registry.
- **Adapters** — файлы, Compose, Docker, Caddy, Master API, locks (файловый I/O),
  кэш. Процессы и сеть — только здесь.
- **Composition root** (`cli.py`) собирает реализацию один раз; тесты подменяют
  **порты**, а не имена helper'ов CLI-модуля (ключевое отличие от текущего кода,
  где тесты патчат `apps_platform.cli.<helper>`).
- **Typer-команды** живут в `commands/` рядом с use cases того же файла: в
  `commands/*.py` пара «typer-обработчик (тонкий) + use case (логика)» —
  обработчик не содержит правил; это единственное место, где Typer-типы
  (`typer.Option`) допустимы.

### 10.3 Размещение модулей

```text
apps_platform/
├── cli.py                  # фабрика приложения и composition root
├── commands/               # Typer-обработчики + use cases (§10.2)
│   ├── status.py           #   обзор, watch
│   ├── service.py          #   list, create, deploy, stop, start, restart, logs
│   ├── diagnostics.py      #   validate, server
│   ├── backups.py          #   create, list, restore, delete
│   ├── platform_ops.py     #   proxy reload, info
│   └── legacy.py           #   заглушки старых команд (§7.5)
├── core/                   # домен
│   ├── models.py           #   ServiceRef, Route, SectionResult, Finding,
│   │                       #   FixSuggestion, DeploymentResult, enums статусов
│   ├── errors.py           #   доменные исключения + классификация → exit/код
│   └── validators/         #   чистые проверки
│       ├── manifest.py
│       ├── runtime.py
│       ├── network.py
│       ├── caddy.py
│       └── diag_server.py  #   проверки diag server (P6)
├── sources/                # I/O adapters
│   ├── filesystem.py       #   discovery, манифесты, project root
│   ├── compose.py          #   запуск docker compose
│   ├── docker.py           #   статусы, сети, stats, логи, inspect
│   ├── caddy.py            #   чтение conf.d/*.caddy
│   ├── master.py           #   Master API (обёртка api_client)
│   ├── locks.py            #   LockManager (файловый I/O → адаптер)
│   ├── cache.py            #   кэш снапшотов completion (§14)
│   └── journal.py          #   журнал операций (§13.5)
├── ui/
│   ├── console.py          #   Console, NO_COLOR/TTY-политика
│   ├── renderers/          #   text / json / ndjson presenter'ы
│   ├── widgets.py          #   таблицы, панели, статус-маркеры
│   ├── prompts.py          #   questionary-обёртки (вывод в stderr/TTY)
│   └── progress.py         #   деплой-прогресс, Live для --watch
└── config.py               #   ops-config + user config + env (§11.1)
```

### 10.4 Ключевые контракты домена

**SectionResult**:

```text
SectionResult:
  state: complete | partial | unavailable
  data: typed value | absent
  observations: [Observation]   # по одному на источник: source, observed_at, stale, note
  findings: [Finding]           # уровни error/warning — то же, что в validate
```

`Observation.source ∈ {filesystem, docker, caddy, master, direct_probe}`.
Отдельного поля `warnings` нет — предупреждения это `Finding` с
`level: warning` (устраняет дублирование моделей).

**Finding**:

```text
Finding:
  level: error | warning | note
  check: str                    # id проверки: manifest/visibility-dir и т.п.
  service: ServiceRef | absent
  object: str                   # манифест, контейнер, сеть, маршрут
  message: str                  # человеческий текст (§7.6)
  fix: FixSuggestion | absent
```

**FixSuggestion** (замена прежнего плоского `fix: str`):

```text
FixSuggestion:
  description: str              # что меняет
  root_cause: str | absent      # корневая причина, если fix — временное средство
  commands: [[argv...]]         # готовые команды argv-массивами; НЕ исполняются
  risky: bool                   # mv запущенного сервиса и т.п. — помечается
```

**ValidationReport** (полная структура, вместо «списка Finding»):

```text
ValidationReport:
  schema_version: 1
  scope: all | [ServiceRef...]      # вся платформа или выбранные сервисы
  started_at / finished_at: timestamp
  observations: [Observation]       # какие источники опрашивались, свежесть
  findings: [Finding]
  summary:
    errors: int
    warnings: int
    notes: int
    services_ok: int
    services_with_findings: int
```

**DeploymentResult**:

```text
DeploymentResult:
  service: ServiceRef
  plan: [DeployStep]            # preflight, build, pull, up, routing, postcheck
  steps: [StepOutcome]          # state ok|skipped|failed, длительность, причина
  postcheck: SectionResult | absent   # только свежая проба
  elapsed: duration
```

### 10.5 Миграция существующего кода

| Сейчас | Куда | Правки |
|---|---|---|
| `cli.py`: `get_project_root()`, `get_config()` | `config.py` + `sources/filesystem.py` | без правок логики; добавить `--project-dir` |
| `cli.py`: `get_services()` | `sources/filesystem.py` → `ServiceRef` | структурированный возврат |
| `cli.py`: `platform_lock()` | `sources/locks.py` → порт `LockManager` | scoped-версия, §13.4; `O_NOFOLLOW` сохраняется |
| `cli.py`: `compose_cmd()`, `get_service_status()` | `sources/compose.py`, `sources/docker.py` | уходят из CLI-модуля: процесс — адаптер |
| `service_inspection.py` | `sources/docker.py` + чистые парсеры в `core` | убрать ре-экспорты для тестовых патчей |
| `caddy_parser.py` (`parse_caddy_config`) | парсер — `core` (pure), чтение файлов — `sources/caddy.py` | разделение pure/IO |
| `api_client.py`: `get_api_client()` | `sources/master.py` | убрать импорт `from .cli import ...` (сейчас `get_api_client` тянет `_get_ssl_verify` из CLI-модуля) |
| `commands/services.py`, `services_create.py`, `services_listing.py`, `backups.py` | `commands/service.py`, `commands/backups.py` | логика → use cases, обработчики тонкие |
| `scripts/validate.py`: `validate_service()` | `core/validators/{manifest,runtime,network}.py` | проверки → домен, вывод → presenters |
| `docs/diagnostics/diagnose-server.sh` | `core/validators/diag_server.py` + `commands/diagnostics.py` | поэтапно (§15.3); bash не удаляется до parity |
| `docs/diagnostics/diagnose-client.sh`, `diagnose-all.sh` | **не портируются** — решение §15.4 | остаётся вне CLI |
| `tests/test_cli.py` и др. | тесты на портах/adapters | патчи `apps_platform.cli.<helper>` запрещены |

---

## 11. Источники данных, деградация и среда

### 11.1 Конфигурация и окружение

**Приоритет разрешения project root** (первый найденный выигрывает):

1. `--project-dir PATH` (CLI, авторитарный);
2. `OPS_PROJECT_ROOT` env;
3. маркер `.ops-root` вверх от CWD;
4. `project_root` из системного конфига;
5. CWD (совместимость).

**Приоритет настроек**: CLI-флаг > env > user config (`~/.config/platform/…`,
только preferences) > `.ops-config.yml` проекта (source of truth платформы).

**Env-переменные**:

| Переменная | Назначение |
|---|---|
| `OPS_PROJECT_ROOT` | явный project root (dev/CI) |
| `OPS_CONFIG_PATH` | путь к ops-конфигу |
| `PLATFORM_API_TOKEN` | Bearer-токен Master API (только env, не конфиг) |
| `PLATFORM_ENV` | `production` — TLS verify принудительно |
| `PLATFORM_SSL_VERIFY` | `false` — отключить verify вне production |
| `NO_COLOR`, `TERM` | отключение цветов (§12.1) |
| `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, `XDG_RUNTIME_DIR` | стандартные пути |

**Master API**: URL — `master_url` из `.ops-config.yml` (дефолт
`http://localhost:8001`); TLS — verify по умолчанию, отключение вне production
только env-флагом; токен — из env (§16). Несовместимость версий CLI ↔ Master:
`info` показывает версии; при несовместимом API — структурная ошибка
`master_incompatible` с версиями, никогда не traceback.

### 11.2 Матрица деградации (команда × источник)

| Команда | ФС | Docker | Caddy | Master | Отказ обязательного → exit |
|---|---|---|---|---|---|
| `status` | обяз. | опц.¹ | опц.¹ | опц. | ФС → 3 |
| `service list` | обяз. | — | — | — | ФС → 3 |
| `service create` | обяз. | опц.² | опц. | — | ФС → 3 |
| `service deploy/stop/start/restart` | обяз. | **обяз.** | опц.³ | опц.³ | Docker → 3 |
| `service logs` | обяз. | **обяз.** | — | — | Docker → 3 |
| `backup *` | опц. | — | — | **обяз.** | Master → 3 |
| `diag validate` | обяз. | опц.⁴ | опц. | — | ФС → 3 |
| `diag server` | обяз. | **обяз.** | обяз. | опц. | любой обязательный → 3 |
| `proxy reload` | — | **обяз.** | — | — | Docker → 3 |
| `info` | опц. | опц. | опц. | опц. | всегда 0 (это отчёт) |

¹ Опциональный источник → секция unavailable, exit 0 + partial по умолчанию;
`--strict` → 3 (§8.3). Скриптам-мониторам: `status --strict` или `--json`.
² Docker нужен только для проверок занятости порта; недоступен → warning.
³ `routing`-шаг деплоя при недоступном Master → warning «маршрут может быть не
сгенерирован» (§9.2); генерация `conf.d/*.caddy` — обязанность Master (с
шаблонами в `_core/caddy/templates`), поэтому при живом Docker, но мёртвом
Master маршрут может отсутствовать — postcheck/routing-шаг это ловит.
⁴ Docker-проверки пропускаются с note «Docker недоступен — runtime не проверен»;
error-findings из статических проверок → exit 4.

Правило: **отказ опционального источника никогда не маскируется под успех и не
блокирует остальные секции**; отказ обязательного — exit 3 со структурной
ошибкой (§12.4).

### 11.3 Свежесть по источникам

| Источник | Свежесть |
|---|---|
| filesystem | перечитывается на каждый вызов — всегда свежая |
| docker / direct_probe | момент вызова |
| caddy | момент вызова (файлы) |
| master cache | свежий ≤ `health.stale_after` (90с), дальше `stale: true` |

Кэшированные данные Master никогда не показываются как результат прямой пробы:
в `observations` источник и возраст видны всегда.

### 11.4 Правило «не показывать, чего не знаем»

Поля «последний деплой» и «версия» не вычисляются и не показываются до
авторитетного источника deployment metadata (§19, Q3). Image digest можно
показывать как digest, но не как время деплоя.

### 11.5 Среда выполнения

- **Основной режим — запуск на хосте** (Linux): прямой доступ к docker.sock,
  bind-mount'ы compose корректны. Linux-only задокументировано
  (`/run/lock`, `$XDG_RUNTIME_DIR`).
- **Контейнерный образ CLI** (существующий Dockerfile): поддерживается только
  для **read-only** команд (`status`, `list`, `diag validate`, `info`).
  Мутации из контейнера отключены структурно (`environment_mismatch`, exit 3):
  запуск `docker compose` из контейнера ломает относительные bind-mount'ы.
- Требуемое окружение: Docker ≥ 20.10, docker.sock доступен, Python 3.11+
  (или wheel со своим интерпретатором — pipx).
- Совместимость CLI ↔ Master по версиям — §11.1.

### 11.6 Производственная база (срез 2026-10-06) и правила сопоставления

Срез прода `/apps` — источник фикстур и регрессионных целей (Приложение F):
Docker Engine + Compose v5.0.0, Caddy 2.11.2 (admin API на 127.0.0.1:2019),
15 контейнеров / 8 compose-проектов, 10 сервисов (4 core, 4 public, 2 internal).

**11.6.1 Сопоставление контейнер ↔ сервис** — по надёжным данным, не по
эвристикам имён:
1. `com.docker.compose.project == <имя сервиса>` — primary (на проде совпадает
   для всех: support, urfu-forms, imap-proxy, course-archive-explorer, caddy,
   master);
2. метка `platform.service` — secondary (встречается на части контейнеров);
3. эвристика имён (`_matches_service`) — fallback для контейнеров без
   compose-меток.

Причина: имена контейнеров нестабильны — `urfu_forms_backend` (подчёркивания),
`course-archive-explorer-frontend-1` (суффикс индекса), `support-zammad-web`.

**11.6.2 Метки платформы**: `platform.service`, `platform.visibility`,
`platform.version`, `platform.managed=true` частично заполнены на проде;
wizard проставляет их генерируемому compose (Приложение B); их отсутствие —
note валидатора, не error.

**11.6.3 Известные баги v1** — регрессионные цели P2 (в v2 не воспроизводить):
1. `platform status` без аргумента — пустая таблица;
2. URL-мусор в `list`: `https://tls`, `https://@sentry`,
   `https://apps.openedu.urfu.ru@sentry`, чужие URL в строке caddy;
3. urfu-forms показан «stopped» при 3 живых контейнерах (подчёркивания против
   дефисов — мотивирует 11.6.1);
4. imap-proxy — заглушка `http://localhost:8000` вместо «URL нет»;
5. память показывается только для первого контейнера;
6. колонка `Available: ?` без данных.

**11.6.4 Дополнения Master API (заглушки)** — конкретные роуты/схемы
определяются на этапе ТЗ Master; CLI не ждёт их реализации:
- `<TBD health-snapshot>` — свежие результаты HealthChecker для секции health
  (§8.1) и истории «падает N мин»;
- `<TBD deployments-metadata>` — честные «последний деплой/версия» (§11.4);
- `<TBD lock-координация>` — участие Master в `.platform-locks/` (§13.4).

---

## 12. Контракты CLI

### 12.1 Форматирование и потоки

- TTY: человекоориентированный вывод; таблицы адаптируются к ширине
  (60/80/120 — покрыты golden-тестами, §18.2).
- Перенаправление stdout: цвета/анимация убираются, записи построчные
  (пайпы в `grep`/`jq` работают).
- `NO_COLOR`, `TERM=dumb`, `--no-color` учитываются независимо от presenter'а.

### 12.2 JSON и NDJSON

- Успешный `--json` — **только JSON в stdout**; корень — объект с
  `schema_version` (N8), никогда top-level массив.
- Human progress/warnings — в **stderr**; JSON-ошибка — тоже в **stdout**
  (машинный контракт не смешивается с данными; человек видит её последним
  перед exit).
- `logs --follow --json`, `status --watch --json` — NDJSON: запись на событие.

**Примеры успешных ответов** (все — объекты):

```jsonc
// platform service list --json
{
  "schema_version": 1,
  "source": "filesystem",
  "observed_at": "2026-10-06T12:00:00Z",
  "services": [
    {"name": "api", "visibility": "public", "routing": "domain",
     "url": "https://api.example.test", "path": "services/public/api"}
  ]
}

// platform status --json  (partial: Master недоступен)
{
  "schema_version": 1,
  "complete": false,
  "sections": {
    "services": {"state": "complete", "data": [/* ServiceRef-статусы */]},
    "health":   {"state": "unavailable",
                 "observations": [{"source": "master", "note": "connection refused"}]},
    "problems": {"state": "complete", "findings": [/* Finding[] */]}
  },
  "summary": {"attention": 2, "problems": 2}
}

// platform service deploy api --build --json
{
  "schema_version": 1,
  "service": "api",
  "steps": [
    {"step": "preflight", "state": "ok", "elapsed_s": 0.1},
    {"step": "build",     "state": "ok", "elapsed_s": 28.1},
    {"step": "up",        "state": "ok", "elapsed_s": 2.3},
    {"step": "routing",   "state": "ok"},
    {"step": "postcheck", "state": "ok", "health": "ok"}
  ],
  "elapsed_s": 31.2
}

// platform diag validate --json  — ValidationReport, §10.4
```

### 12.3 Ошибки для человека

Сообщение отвечает на четыре вопроса: что произошло, с каким объектом, что CLI
успел сделать, что проверить/запустить дальше (пример в §9.2). Traceback —
только `--verbose`. Секреты не выводятся (§16).

### 12.4 Exit codes и реестр кодов ошибок

**Exit codes** (единственный владелец — этот раздел):

| Код | Значение |
|---|---|
| `0` | Успех; для status — возможен явно описанный partial |
| `1` | Ошибка выполнения операции/сервиса (шаг деплоя, postcheck, compose) |
| `2` | Ошибка аргументов/конфигурации, исправимая пользователем; нехватка обязательного ввода в non-TTY; неизвестная секция в `--sections`; заглушка старой команды |
| `3` | Обязательная зависимость недоступна (матрица §11.2); `--strict` и недоступная секция; environment mismatch |
| `4` | `diag validate`/`diag server` завершились с findings уровня `--fail-on` (дефолт error) |
| `130` | Прервано Ctrl-C |

**Реестр кодов ошибок JSON** (закрытый; `code → exit → hint`):

| `code` | exit | hint (шаблон) |
|---|---|---|
| `arg_missing` | 2 | «передайте … или уберите --no-input» |
| `service_not_found` | 2 | «platform service list --json» |
| `service_exists` | 2 | «выберите другое имя» |
| `name_invalid` | 2 | правила имени (§13.3) |
| `port_conflict` | 2 | «порт занят: …» |
| `section_unknown` | 2 | допустимые секции |
| `no_tty` | 2 | «операция требует интерактива или --yes/--no-input» |
| `invalid_value` | 2 | допустимые значения |
| `config_not_found` | 3 | «запустите ./install.sh или задайте OPS_CONFIG_PATH» |
| `docker_unavailable` | 3 | «проверьте docker ps» |
| `master_unavailable` | 3 (для backup) / warning (иначе) | «platform info» |
| `master_incompatible` | 3 — только для команд, требующих Master (`backup *`); `info` — exit 0 + отчёт о несовместимости | версии CLI/Master |
| `environment_mismatch` | 3 | «мутации недоступны из контейнера» |
| `lock_busy` | 3 | «выполняется другая операция (lock: …); --wait N» |
| `compose_failed` | 1 | шаг, stderr в панель |
| `step_failed` | 1 | шаг деплоя, атрибуция |
| `postcheck_failed` | 1 | «сервис запущен, health failing → logs» |
| `snapshot_not_found` | 2 | «platform backup list <svc>» |
| `restore_conflict` | 2 | конфликт перезаписи; «повторите с --force» |
| `cancelled` | 130 | — |
| `internal_error` | 1 | «повторите с --verbose и сообщите баг» |

Exit выбирается **по типу причины** (классификация в `core/errors.py`), не по
общему типу исключения.

### 12.5 Матрица интерактивности

| Ситуация | Поведение |
|---|---|
| TTY, мутация, без `--yes` | подтверждение с последствиями |
| TTY, подтверждение, явный отказ (N) | exit 0 («операция отменена»), ничего не изменено; отличается от Ctrl-C (130) |
| TTY, `--yes` | без подтверждения |
| non-TTY, мутация, без `--yes` | **exit 2** (`no_tty`), операция не выполняется |
| non-TTY, мутация, `--yes` | выполняется молча |
| `--no-input` + нехватка обязательного ввода | exit 2 + подсказка |
| `--json` | подразумевает `--no-input`; если пользователь явно запросил интерактив — конфликт → warning, prompt'ы отключены |
| Ctrl-C в prompt или операции | exit 130, ничего не изменено, lock освобождён |

Prompt'ы рисуют **только в stderr/tty** (никогда в stdout) — `--json` и пайпы
в `less` не ломаются.

---

## 13. Интерактив, подтверждения, мастера и locks

### 13.1 Правила prompt'ов

Prompt — только для отсутствующих обязательных значений, только TTY (§5.4),
с отменой (§12.5), выбор через questionary (`select` + `use_search_filter`).

### 13.2 Подтверждения

Перечень — §5.5; `--yes` — пропуск; non-TTY без `--yes` → exit 2; параметры
операций не подменяются.

### 13.3 Мастер `service create`

Шаги (каждый спрашивается, если нет соответствующего флага; `--no-input`/non-TTY
требует полного набора):

1. **Имя**: regex `[a-z0-9][a-z0-9_-]{0,62}` (строчные — совместимость с
   compose project name и DNS-label 63; заглавные/точки запрещены), проверка
   занятости.
2. **VIS**: public / internal.
3. **Роутинг**: `domain` | `subfolder` | `port` | `none`. Разграничение:
   `port` — сервис, который надо **проксировать по порту** (правило routing
   генерируется); `none` — HTTP-роутинга нет вообще (TCP/imap: манифест
   получает явный маркер `routing: none`, Приложение B). Забытое поле `routing`
   ≠ осознанное `none` (§15.2).
4. **Адрес**: для domain/subfolder — домен (формат, занятость по caddy-конфигам)
   / путь; для port — порт (диапазон, занятость по `docker ps` + манифестам
   других сервисов + слушателям хоста, если доступно); для none — шаг пропускается.
5. **container_name** (дефолт `{name}-{role}`, роль из compose) и
   **internal_port** — по требованиям валидатора; для `none` достаточно
   container_name.
6. **health.endpoint** (опционально): флаг `--health-endpoint`; без него —
   `health не настроен` (не ошибка).
7. **backup** — `--backup {on,off}`; без флага — вопрос в TTY, дефолт off.
8. **Preview** — сгенерированный `service.yml` + каркас compose целиком;
   подтверждение в TTY, **пропускается, если все параметры даны флагами**
   (тогда `--yes` не нужен).
9. **Запись** — атомарно: файлы пишутся во временный каталог внутри
   `services/<vis>/<name>/`, затем переименовываются; `service.yml` —
   **последним** (маркер завершённости для discovery, §17.3). `--dry-run` —
   только печать.

### 13.4 Lock-политика (владелец правила)

- **Механизм**: `flock(LOCK_EX|LOCK_NB)` на lock-файле; kill -9 → lock
  освобождается ядром автоматически, файл-флаги с stale-проверками не
  используются.
- **Каталог** (решение Q9=(a), Прил. A14): `.platform-locks/` в корне проекта
  (рядом с маркером `.ops-root`, общий mount — виден всем операторам);
  fallback `/run/lock/platform/` (0770). **Не** `$XDG_RUNTIME_DIR`
  (пользовательский каталог — операторы с разными UID не видят lock'и друг
  друга).
- **Scope**: сервисные мутации — lock на сервис (`{project}-{service}.lock`);
  `proxy reload` — глобальный lock; read-only — без lock.
- **Порядок**: lock берётся **после** prompt'ов и валидации; внутри секции
  состояние перепроверяется.
- **`--wait N`**: ожидание освобождения, дефолт 0 (сразу отказ). Отказ →
  `lock_busy` exit 3 с путём lock-файла.
- **Согласование с Master** (решение Q9=(a)): в v1 Master не координируется —
  ноль доработок Master; конфликтное окно фиксируется журналом операций
  (§13.5) и postcheck'ом. Допустимое будущее дополнение Master API — участие
  в `.platform-locks/` (заглушка §11.6.4).

### 13.5 Журнал операций

- Append-only журнал мутаций: время, пользователь (uid), команда, объект,
  результат, длительность. Расположение: `<project>/.platform-journal.log`
  (JSON-строки).
- Назначение: аудит «кто и когда задеплоил/перезапустил/восстановил»; частично
  отвечает на Q3 (metadata деплоя) без нового хранилища.
- `platform info` показывает путь журнала и последние записи.

### 13.6 Семантика restart

`service restart` = `docker compose restart` (сохраняет контейнеры и их
конфигурацию). Пересоздание (например, после правки compose) — явный
`deploy`. Текст подтверждения соответствует реальной операции.

---

## 14. Completion

- **Имена сервисов — напрямую из ФС** (`scandir` двух каталогов): быстрее и
  свежее любого TTL-кэша; completion горячий путь — только ФС.
- **Кэш — только для снапшотов Master** (`backup`): `~/.cache/platform/`
  (XDG-стандарт, единый корень с конфигом `~/.config/platform/`), TTL 30с,
  stale fallback, atomic write (tmp+rename), project identity в ключе,
  повреждённый файл игнорируется и перезаписывается.
- **Ленивые импорты**: старт CLI ≤ 150мс — precondition для ≤ 100мс completion
  (§17.4); тяжёлые зависимости (docker, questionary, master-клиент) грузятся в
  команде, не при старте.
- `platform --install-completion` добавляется в `install.sh`.

---

## 15. Диагностика

### 15.1 Единая модель

Все проверки → `ValidationReport` (§10.4). Секция `problems` в status —
**лёгкое подмножество**: проверки `manifest` (файлы, уже прочитанные
discovery), `caddy`-дубли (файлы), `network/membership` и `runtime/running`
(один батч docker inspect из уже собранных статусов). Никаких HTTP-проб в
status. Стоимость каждой проверки помечена в §8.1 и в `--json` отчёте
(`cost: cheap|medium|expensive`).

### 15.2 `diag validate`

| Группа проверки | Содержимое |
|---|---|
| `manifest/*` | наличие service.yml; YAML; visibility ↔ директория (два корректных фикса, §9.4); `routing` отсутствует → **warning** «если сервис без HTTP-роутинга — задайте routing: none» (забытое поле ≠ осознанное); `routing: none` → note; для каждой routing-записи: `container_name`, `internal_port` — число; `health.endpoint` структурно корректен |
| `runtime/*` | контейнеры из routing запущены; unhealthy фиксируется |
| `network/*` | `platform_network: external: true` в compose; членство контейнеров; fix указывает корневую причину (compose), `docker network connect` — с пометкой `risky`/временное |
| `caddy/*` | дубли доменов; маршруты без бэкенда |

- Фильтры: `--check ID...`, `--level {error,warning,note}...`, scope —
  `[SERVICE...]` (позиционные, все = вся платформа).
- **`--fail-on {error,warning,none}`**, дефолт `error`: findings указанного
  уровня → exit 4; иначе 0. Warnings без errors → 0 (CI может поставить
  `--fail-on warning`).
- **Ignore-list**: config `diag.ignore: [{check, service, reason}]` или
  `--ignore-file`; подавленные findings помечаются `suppressed: true` в JSON,
  в человекочисленном выводе — одной строкой. Без ignore-list CI-гейт и
  `problems` шумят вечно.
- Коды: ошибки → `4`; обязательная ФС недоступна → `3`; Docker недоступен →
  runtime/network-проверки пропущены с note (§11.2⁴).

### 15.3 `diag server` — порт diagnose-server.sh

Ключевой факт скрипта: имя сервиса часто **не совпадает** с первой меткой
домена (`support` → `help.openedu.urfu.ru`), поэтому цель резолвится по домену
в `routing[]`.

- **Exit code**: findings уровня `--fail-on` → 4 (та же модель, что validate).
- **Проверки** (перенос из bash, §18.1 P6): резолвинг манифеста по имени/домену;
  контейнер запущен/healthy; членство в network; конфиг Caddy (сгенерирован,
  бэкенд совпадает); admin API Caddy (маршрут живой); прямые HTTP/TCP пробы;
  core-контейнеры master/caddy; последние ошибки логов.
- **Вывод**: человеко — поэтапный отчёт с provenance; `--json` —
  ValidationReport.
- **Packaging (Q4=(a), закрыт, Прил. A15)**: до полного порта
  `diagnose-server.sh` поставляется asset'ом wheel'а
  (`apps_platform/data/diagnose-server.sh`); `platform diag server` — тонкая
  обёртка, исполняющая его; read-only инвариант сохраняется. После порта asset
  удаляется. `diagnose-all.sh` asset'ом не становится — его функция покрывается
  `diag validate` (§15.4).
- bash-оригинал не удаляется до parity (§18.1 P6).

### 15.4 Судьба diagnose-client.sh и diagnose-all.sh (решение)

- `diagnose-client.sh` **не портируется**: клиентская машина может не иметь
  docker/docker.sock — это другая среда, не задача CLI. Остаётся самостоятельным
  скриптом со ссылкой из `platform info` (docs/diagnostics).
- `diagnose-all.sh` — обёртка над серверными проверками; его функция покрывается
  `platform diag validate` (все сервисы) — удаляется после parity `diag server`.

Read-only инвариант обеих diag-команд: только чтение (docker ps/inspect/logs/
network inspect, ls, grep, HTTP GET), ничего не меняется.

---

## 16. Безопасность

- **Docker socket — привилегированный доступ к host**; CLI не понижает и не
  скрывает границу.
- **Внешние процессы**: argv-массив без shell, заданный cwd, timeout;
  stderr/timeout отражаются в диагностике.
- **Секреты**: не в выводе (включая `--verbose`); токен — только env (§11.1).
- **Lock-файлы**: `O_NOFOLLOW`, права 0600 (в общем каталоге — с учётом
  группы); symlink-атаки исключены.
- **Кэш**: project identity, atomic write, повреждённый файл игнорируется.
- **Конфиг**: user config не может переопределять source of truth платформы.

---

## 17. Производительность

### 17.1 Бюджеты и параллельность

| Операция | Бюджет | Механизм |
|---|---|---|
| `status` | ≤ 2с на 10 сервисов (`status.deadline`, конфиг; при инциденте поднимается) | **параллельный опрос источников** (N10); прогрессивный вывод: секции печатаются по мере готовности; дедлайн истёк → partial |
| `resources` | свой бюджет (не входит в дефолтный) | `docker stats` ≥1с — секция только по запросу (§8.1) |
| completion | ≤ 100мс p95 | ФС scandir + кэш снапшотов; без docker/сети |
| старт CLI | ≤ 150мс | ленивые импорты (§14) |

Дедлайн — общий на команду, не сумма timeout'ов; по истечении показываются уже
собранные секции, несобранные отмечены.

### 17.2 Watch и пробы

- Прямые health-пробы не чаще `watch.probe_min_interval` (30с); между пробами —
  последний результат с возрастом; общий deadline соблюдается.
- Перекрывающиеся тики watch пропускаются (§8.4).

### 17.3 Discovery

Файловый discovery перечитывается на вызов (§11.3); полусозданный сервис не
виден, пока `service.yml` не записан последним (§13.3).

---

## 18. План работ и тестовая стратегия

### 18.1 Фазы

Приоритеты: MUST-требования (§6.1) закрываются к P4; SHOULD — к P7.

| Фаза | Содержимое | Критерии выхода |
|---|---|---|
| **P0. Решения** | Закрыть открытые вопросы §19 (Q2-обогащение, Q3, Q4, Q6, Q9); зафиксировать грамматику/коды/схемы | Решения записаны в спеке (версия 1.x) |
| **P1. Каркас** | Composition root, error mapping, presenters text/json, config/env (§11.1), порты+adapters скелет, заглушки старых команд (§7.5), опции в любой позиции | CLI-тесты: help, exit codes, stdout/stderr, TTY/non-TTY, `--json`-ошибки |
| **P2. Наблюдение** | `status` (секции, SectionResult, --strict), `service list`, `info`, **лёгкие валидаторы → problems** (manifest, caddy, network, runtime — read-only), мастер-клиент с деградацией | Deadline, freshness/provenance, JSON-схемы, матрица §11.2 покрыта тестами; регрессии багов v1 не воспроизводятся (§11.6.3) |
| **P3. Управление** | `create` (wizard + флаги + атомарная запись), `deploy` (прогресс, routing/postcheck шаги), `stop/start/restart`, scoped locks | dry-run, атрибуция упавшего шага, **Ctrl-C на реальном subprocess**, lock-тесты |
| **P4. Операционные** | `logs` (подсветка/фильтры/NDJSON), `backup` (create/list/restore/delete, `--force`/`--no-wait`), `--watch` | Follow/NDJSON; restore `--target/--force` семантика; watch-тики и Ctrl-C |
| **P5. Диагностика и completion** | `diag validate` полный CLI (фильтры, `--fail-on`, ignore-list, JSON), completion (ФС + кэш снапшотов), тонкая обёртка `diag server` + bash-asset в wheel (§15.3) | Диагностика согласована с problems; CI-гейт-сценарий (Прил. C.5) зелёный |
| **P6. diag server** | Полный порт diagnose-server.sh в `core/validators/diag_server.py` | Parity с bash-скриптом на реальных сервисах; JSON-отчёт |
| **P7. Релиз и удаление legacy** | Parity по командам, обновление README/help, wheel/container (assets), deprecated-сообщение для `ops`, удаление старого CLI-слоя | Установка из wheel и Docker image проверена; заглушки работают; переход обратим |

Точка входа: в бранче — `platform2` (в main переезжает как `platform`;
`install.sh` ставит entry point и completion для финального имени). Примеры в
этой спеке всегда пишутся с `platform`.

### 18.2 Тестовая стратегия (обязательна на каждую фазу)

1. **Unit домена** — модели/валидаторы/политики без I/O.
2. **Adapter-тесты** — fixture/fake (фикстуры docker-вывода, caddy-конфигов,
   манифестов).
3. **CLI subprocess-тесты** — реальный запуск: stdout/stderr, exit codes,
   **TTY/non-TTY** (pty-тесты для prompt'ов/прогресса).
4. **Golden-тесты вывода** — ширина 60/80/120, `NO_COLOR`, стабильные снапшоты.
5. **JSON-схемы** — `schema_version`, обязательные поля, NDJSON-потоки.
6. **Отмена** — Ctrl-C проверяется на реальном subprocess (не fake), начиная с P3.
7. **Smoke на реальном сервере** — финальная проверка фазы (`SERVICES_ROOT`,
   dry-run), не замена детерминированных тестов.

`SERVICES_ROOT` в `scripts/validate.py` переезжает как env-переопределение для
tests/dev (таблица §11.1).

---

## 19. Открытые вопросы

Все блокеры сняты решениями оператора 2026-10-06. Остались только
неблокирующие дополнения Master API (Q2, Q3).

| # | Вопрос | Статус | Итог |
|---|---|---|---|
| Q1 | `platform status` на верхнем уровне | **Закрыт** | Прил. A, A1 |
| Q2 | Health из Master API | Открыт, **не блокирует** | Primary — прямая проба (§17.2); разрешено дополнить Master API endpoint'ом health-snapshot (схема — заглушка §11.6.4) для истории «падает N мин» |
| Q3 | Deployment metadata | Открыт, **не блокирует** | Журнал операций (§13.5) — минимум; дополнение Master API `<TBD deployments-metadata>` разрешено (§11.6.4); поля не показываются до источника |
| Q4 | Packaging `diag server` до полного порта | **Закрыт** | (a) bash как wheel-asset + тонкая обёртка (§15.3) |
| Q5 | Судьба `ops`/старых команд | **Закрыт** | Заглушки + deprecated-сообщение (§7.5, §1.3) |
| Q6 | Стратегия прямой health-пробы | **Закрыт** | container IP + internal_port (primary), published port (fallback), TCP-connect для порт-сервисов |
| Q7 | JSON мутаций и exit для problems | **Закрыт** | `--json` на всех командах (F10); status 0+partial, `--strict`→3; findings не влияют на status-exit |
| Q8 | Судьба `diagnose-client.sh`/`diagnose-all.sh` | **Закрыт** | §15.4 |
| Q9 | Топология развёртывания CLI и общий lock | **Закрыт** | (a): мутации — хост, контейнер — read-only; `.platform-locks/` в корне проекта; Master не координируется в v1 (§11.5, §13.4) |
| Q10 | Заглушки старых команд | **Закрыт** | §7.5 |

---

## 20. Приложения

### Приложение A. Журнал слияния источников (решения)

Источники: redesign-v2.md (A) и platform-cli-product-design.md (B). Итоги
слияния после внешнего ревью:

| # | Тема | Решение |
|---|---|---|
| A1 | Status | Верхнеуровневый `platform status [SERVICE]`, без дубля в `service` (B) |
| A2 | Имя команды создания | `service create` (B); `new` — заглушка |
| A3 | Обслуживание | `proxy reload` в группе; `info` на верхнем уровне (B) |
| A4 | compose_runner, locks, чтение caddy-файлов | В адаптерах (`sources/`), не в домене (B + ревью); caddy-**парсер** остаётся pure в `core` |
| A5 | Lock | Scoped по сервису, flock, общий каталог, после prompt'ов (B + ревью §13.4) |
| A6 | Флаги интерактивности | `--yes` только подтверждения; `--no-input` запрещает всё (B) |
| A7 | Exit codes | 0–4 + 130; `--strict`; `--fail-on` для diag (B + ревью) |
| A8 | Деплой-метаданные | Не показывать до авторитетного источника (B); частично закрывается журналом (§13.5) |
| A9 | Удаление legacy | После parity + wheel/container (B); до этого заглушки (§7.5) |
| A10 | Визуальная система | Единый ui-слой обязателен; рамка не обязательство; цвет не единственный носитель (середина) |
| A11 | Фазовый план | P0–P7 с критериями выхода (B) + детали миграции (A) |
| A12 | Свежесть/деградация | Явный контракт SectionResult с observations (B + ревью) |
| A13 | Матрица деградации, коды ошибок, JSON-примеры, контракт манифеста, приёмка | Добавлены по ревью (§11.2, §12.4, §12.2, Прил. B, Прил. C) |
| A14 | Q9: lock/топология | Решение (a): `.platform-locks/` в корне проекта; Master не координируется в v1; мутации — хост, контейнер — read-only (§11.5, §13.4) |
| A15 | Q4: packaging diag server | Решение (a): bash как wheel-asset + тонкая обёртка (§15.3) |
| A16 | Master API | Дополнения/переписывание отдельных endpoints разрешены оператором; заглушки §11.6.4 |
| A17 | Утверждение | Спека утверждена оператором 2026-10-06; PRD исправлен и влит (Прил. G/H); настоящий документ — итоговое ТЗ |

### Приложение B. Контракт манифеста (`service.yml`)

Спека опирается на эти поля; формальная JSON-схема — задача P1 (fixtures).

```yaml
# services/{public,internal}/<name>/service.yml
name: <name>                    # обяз.; == имени каталога; [a-z0-9][a-z0-9_-]{0,62}
type: docker-compose            # дефолт docker-compose
visibility: public|internal     # обяз.; должен совпадать с каталогом
routing: none |                 # явный маркер «HTTP-роутинга нет» (порт-сервис)
  - type: domain|subfolder|port
    domain: <domain>            # для domain/subfolder (см. base_domain)
    base_domain: <domain>       # для subfolder; path по умолчанию /<name>
    path: <path>                # для subfolder
    port: <int>                 # для port
    internal_port: <int>        # порт контейнера, на который проксирует Caddy
    container_name: <name>      # обяз. для каждой записи
    auto_subdomain: bool        # опц.; <name>.<base>
health:                         # опц.; без него «health не настроен»
  endpoint: <path>              # HTTP GET от проксирующей стороны
backup:                         # опц.
  enabled: bool
  schedule: <cron>              # интерпретируется Master (croniter)
```

Ограничения/правила:

- Роутинг: **один из** типов на запись; комбинирование не поддерживается.
- `routing` отсутствует → validate: warning «задайте `routing: none`, если
  сервис без HTTP-роутинга» (забытое поле ≠ осознанное).
- Compose-файл: `platform_network: external: true` в `networks`; контейнеры —
  члены сети; `container_name` обязателен для проксируемых сервисов.
- Локальные переопределения: `service.local.yml` (не коммитится) — вне скоупа
  изменений v1, только чтение с deep-merge.

### Приложение C. Приёмочные сценарии (Given/When/Then)

C1. **Status при недоступном Master**
Given Master API недоступен, Docker и ФС доступны
When `platform status`
Then exit 0; секции services/problems полные; health: unavailable с причиной
`Master API недоступен`; вывод содержит «Несобрано: …»; human-вывод не содержит
traceback.

C2. **Атрибуция упавшего шага деплоя**
Given у сервиса сломан Dockerfile
When `platform service deploy api --build`
Then exit 1; последняя строка — `✘ build`; панель содержит stderr сборки;
шаги preflight ✔, build ✘; `--json` содержит `steps[]` с `state: failed` на
`build`.

C3. **Follow-логи как NDJSON**
Given сервис пишет логи
When `platform service logs api --follow --json | head -5`
Then 5 NDJSON-строк в stdout; никаких заголовков/прогресса в stdout;
`schema_version` в каждой записи.

C4. **Create без TTY**
Given non-TTY и полный набор флагов create
When `platform service create --name x --visibility public --routing none
--container-name x-main --no-input`
Then файлы созданы атомарно, `service.yml` записан последним; последующий
`diag validate` — exit 0. Given флаг `--routing` отсутствует Then exit 2 с
`arg_missing` и подсказкой.

C5. **CI-гейт validate с ignore-list**
Given в конфиге подавлен один известный finding, в системе ещё один error
When `platform diag validate --json --fail-on error`
Then exit 4; JSON содержит новый finding, подавленный — `suppressed: true`,
не входит в `summary.errors`.

C6. **Restore: последствия и отмена**
Given снапшот S сервиса api, целевой сервис api запущен
When `platform backup restore S --target api` в TTY, Ctrl-C на подтверждении
Then exit 130; сервис не остановлен; ничего не записано; повторный запуск
показывает те же последствия (снапшот, цель, остановка сервиса, перезапись).

C7. **Заглушка старой команды**
When `platform deploy api`
Then stdout пуст, stderr содержит «Стало: platform service deploy api», exit 2.

### Приложение D. Статусные модели

**Статус сервиса** (`STATUS`, маркер → текст-дубль):

| Маркер | Значение | Цвет | Текст |
|---|---|---|---|
| `●` | running | green | `running` |
| `◐` | degraded — часть контейнеров сервиса запущена | yellow | `degraded` |
| `◔` | starting / restarting | yellow | `starting` / `restarting` |
| `◇` | not_deployed — сервис на диске, контейнеров нет (сразу после create) | dim | `not deployed` |
| `○` | exited / stopped | red | `exited` |
| `✳` | unhealthy | red | `unhealthy` |
| `✳` | crash-loop (частые рестарты) | red | `crash-loop` |
| `?` | unknown — всегда с причиной | dim | `unknown: <причина>` |

**Health** (`ok | failing | unknown(reason) | not_configured | not_applicable`):
`not_configured` — нет `health.endpoint` (показывается в секции health, не
пропускается, §9.1); `not_applicable` — порт-сервис с TCP-check пройден;
`unknown(reason)` — деградация/устаревание источника.

**Шаг деплоя**: `ok | skipped | failed | running`.

### Приложение E. Глоссарий

- **ServiceRef** — доменная ссылка: имя, каталог, visibility, путь манифеста.
- **Finding / FixSuggestion / ValidationReport** — §10.4.
- **SectionResult / Observation** — §10.4; provenance — происхождение данных
  (источник, время, свежесть).
- **Composition root** — единственное место сборки зависимостей (`cli.py`).
- **Use case** — сценарий приложения (§10.2).
- **Port** — интерфейс домена к I/O; только на реальных границах.
- **Bounded fallback** — прямая проверка при недоступности мастера с ограниченным
  бюджетом и явной маркировкой.

### Приложение F. Производственная база (срез 2026-10-06, сервер /apps)

F.1 **Окружение**: `/apps`, пользователь `developer`, Linux. Docker Engine
(compose-метки `com.docker.compose.version=5.0.0`), Caddy `caddy:2-alpine`
(2.11.2; 0.0.0.0:80/443, admin API 127.0.0.1:2019). Python-venv валидатора
на сервере: `/opt/val-env`.

F.2 **Инвентарь** (docker ps: 15 контейнеров / 8 compose-проектов):

| Compose-проект | Сервис | VIS | Контейнеров | Сети | Примечание |
|---|---|---|---|---|---|
| caddy | caddy | core | 1 | platform_network | 80/443, admin 2019 |
| master | master | core | 1 | platform_network | 0.0.0.0:8001→8000 |
| support | support | public | 6 | platform_network | zammad-web/worker, vk-bridge, postgres, redis, elasticsearch — все healthy |
| urfu-forms | urfu-forms | public | 3 | platform_network + urfu-forms_internal | backend только в urfu-forms_internal — Caddy напрямую не достанет |
| course-archive-explorer | course-archive-explorer | public | 2 | platform_network | backend на динамическом порте 0.0.0.0:32768→8080 |
| imap-proxy | imap-proxy | internal | 1 | platform_network | порт-сервис; метки `platform.*` заполнены |

Остальные «сервисы» v1 (instructor, sentry, kopia, backup) — контейнеров нет.
Compose-метки присутствуют у всех; `platform.service`/`platform.visibility`/
`platform.version`/`platform.managed` — частично (zammad-web, urfu-forms*,
imap-proxy). Имена контейнеров: `urfu_forms_backend` (подчёркивания),
`course-archive-explorer-frontend-1` (суффикс индекса), `support-zammad-web`.

F.3 **Регрессии v1** (воспроизведены на проде 2026-10-06, в v2 запрещены):
1. `platform status` без аргумента — пустая таблица;
2. `platform list`: URL-мусор `https://tls`, `https://@sentry`,
   `https://apps.openedu.urfu.ru@sentry`; чужие URL в строке caddy
   (межсервисная утечка парсера);
3. urfu-forms «stopped» при 3 живых контейнерах (дефисы/подчёркивания → §11.6.1);
4. imap-proxy: заглушка `http://localhost:8000` вместо «URL нет»;
5. `status support`: память только для первого контейнера из 6;
6. колонка `Available: ?` без данных.

F.4 **Baseline parity** (цели для diag-команд):
- validate.py на проде: instructor — контейнер не запущен; urfu-forms — нет
  `platform_network: external` в compose; sentry — routing[0] без
  `container_name` + нет network-объявления; imap-proxy — routing
  отсутствует (note). Итого 4 error-finding'а, exit 4.
- diagnose-all.sh ONLY=support: OK:18 FAIL:0 WARN:1.

F.5 **Заглушки Master API** (см. §11.6.4): `<TBD health-snapshot>`,
`<TBD deployments-metadata>`, `<TBD lock-координация>`. Схемы и роуты —
задача ТЗ Master; до реализации соответствующие поля/секции CLI показывают
как «не настроено/недоступно».

F.6 **Фикстуры**: сырые срезы этого обсуждения сохраняются в
`tests/fixtures/prod-2026-10-06/` (docker-ps.jsonl, caddy-conf.d/*.caddy,
manifests/*.yml, platform-list-output.txt, validate-output.txt,
diagnose-support.txt) — задача P1 (test harness).

### Приложение G. Пользовательские истории (влито из PRD v1.1)

Оператор платформы:

- **US-O1**: видеть обзор платформы одной командой `platform status` — сколько
  сервисов работают, сколько требуют внимания. *(F2, §8.3)*
- **US-O2**: видеть для каждого наблюдения источник, время и свежесть, чтобы
  отличать «не настроено» от «не удалось проверить». *(§5.2)*
- **US-O3**: получать в выводе явный следующий шаг (`platform service logs api
  --since 10m`). *(§4)*
- **US-O4**: Ctrl-C не ломает данные (exit 130, lock освобождён, ничего не
  изменено). *(§5.7)*
- **US-O5**: журнал мутаций «кто/когда/что/итог» — «кто задеплоил в 3 ночи». *(F18, §13.5)*
- **US-O7**: `platform info` с версиями CLI и зависимостей, путями и
  состоянием окружения, чтобы отличать проблему окружения CLI от проблемы
  платформы. *(F14, §7.2)*

Разработчик сервиса:

- **US-D1**: создать сервис через мастер `service create` без ручного набора
  манифестов. *(F5, §13.3)*
- **US-D2**: деплой с пошаговым прогрессом и атрибуцией упавшего шага. *(F3, §9.2)*
- **US-D3**: логи с подсветкой уровней и `--since/--grep/--container`. *(F4, §9.3)*
- **US-D4**: restart с подтверждением последствий — не уронить публичный URL
  случайно. *(§5.5)*
- **US-D5**: автодополнение имён сервисов и снапшотов. *(F9, §14)*
- **US-D6**: `service start` — поднять остановленный сервис без полной
  пересборки. *(F17, §7.3)*

CI / скрипт / cron:

- **US-C1**: `--json` на всех командах с `schema_version` — парсить без
  хрупкого разбора текста. *(F10, N8)*
- **US-C2**: гарантия «никогда не prompt'ит» в non-TTY и под `--no-input`. *(§12.5)*
- **US-C3**: строгие exit codes 0/1/2/3/4/130 — гейтить по типу причины. *(§12.4)*
- **US-C4**: `diag validate --fail-on` с ignore-list — известные findings не
  шумят вечно. *(F7, §15.2)*
- **US-C5**: заглушки старых плоских команд с подсказкой замены — старые
  вызовы падают понятно. *(F16, §7.5)*

Backup / восстановление (оператор, CI):

- **US-B1**: restore снапшота с показом последствий (снапшот, целевой сервис,
  остановка сервиса, семантика перезаписи) и безопасной отменой. *(C6, §5.5)*
- **US-B2**: `backup list` с возрастом и размером снапшотов. *(§7.2)*
- **US-B3**: `restore --no-wait` — вернуть job id, не блокировать пайплайн. *(§7.4)*

Story map (критический путь): status (observe) → diag validate (explain) →
deploy/restart (act) → status/postcheck (verify); create — входная точка
нового сервиса; backup — отдельная ветка жизненного цикла.

### Приложение H. Метрики успеха (влито из PRD, утверждено)

| Метрика | Цель | Базовая линия |
|---|---|---|
| Время до диагноза оператором (запуск → понимание проблемы) | ≤ 30 секунд, 1 команда | история терминала + 3–4 скрипта |
| Доля операций через CLI (не прямые docker/скрипты) | ≥ 80% за 3 месяца после релиза | ~0% |
| Бюджеты производительности (§17.1) | status ≤ 2с · completion ≤ 100мс p95 · старт ≤ 150мс | не измерялись |
| CI-гейт `diag validate` | зелёный на чистой платформе, красный при error-findings | validate.py ad-hoc |
- **Wizard** — интерактивный мастер `service create` (§13.3); **Master** —
  Platform Master Service (внешний сервис). В документе «мастер» означает
  только wizard.