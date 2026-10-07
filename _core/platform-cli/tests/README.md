# Тесты platform-cli

## Запуск

```bash
python -m pytest tests/ -q                  # весь контур (регрессия P1)
python -m pytest tests/test_cli_v2.py -q    # subprocess: help/exit/каналы/golden
python -m pytest tests/test_tty.py -q       # TTY/non-TTY через pty
ruff check tests/test_cli_v2.py tests/test_tty.py tests/fixtures/
black tests/test_cli_v2.py tests/test_tty.py tests/fixtures/
```

Требуется установленный entry point: `python -m pip install -e .` → команда
`platform2` в `PATH` (subprocess-тесты запускают именно её, а не `python -m`).

### Известные падения полного прогона (25, НЕ чинить в P1)

Полный `python -m pytest tests/ -q` даёт **ровно 25 failed** — это
**прекестовый baseline v1** (диагностировано 2026-10-06, бэклог P1,
«Известный долг v1»; удаляется вместе с v1 в P7):

| Файл | Кол-во | Причина |
|---|---|---|
| `tests/test_api_client.py` | 14 | патч `aiohttp.ClientSession` (AsyncMock) не перехватывает создание сессии внутри `api_client` — падает на реальном событийном цикле/сессии |
| `tests/test_cli.py` | 11 | коллайдер имён: плоский `backup <svc>` v1 перехватывается группой `backup create` (падают `TestBackupCommands::test_backup_*`) + `TestValidateServiceName::test_rejects_129_chars` |

**Что НЕ чинить в P1** (границы T11): эти 25 падений; любой «фикс» через
правку `legacy_cli.py`/v1-команд/`api_client.py` — рефакторинг замороженного
v1 (tech spec §10.10, принцип 10) и выходит за скоуп каркаса. Критерий T11 —
«не хуже baseline»: новых падений 0, `passed` ≥ 410, `xfailed` 0.

Ожидаемый результат полного прогона P1: `25 failed, 411 passed` (все 25 —
v1-baseline сверху).

## Subprocess-контур (T10)

`tests/test_cli_v2.py` и `tests/test_tty.py` гоняют `platform2` **отдельными
процессами** (`subprocess.run`, таймаут 30 s) из `tmp_path` — реальный контур
`[project.scripts]`, без docker/сети/глобальных путей.

Всё, что нужно для запуска, — в `tests/fixtures/`:

| Файл | Назначение |
|---|---|
| `support.py` | `make_env` (изолированное детерминированное окружение: конфиг-env снят, `XDG_CONFIG_HOME`/`COLUMNS`/`TERM` в tmp, `NO_COLOR=1`/`PYTHONUTF8=1` дефолтом; `None` в overrides удаляет ключ), `run_platform2`/`run_fixture` (запуск с `capture_output`+таймаутом), `run_platform2_tty` (два pty: stdout и stderr — разные slave-пары, каналы различимы, `isatty()` истинно), `make_ops_project` (tmp-проект: `.ops-root` + `.ops-config.yml` + `services/public/demo/docker-compose.yml`), `normalize_help`/`strip_ansi` |
| `boundary_cli.py` | харнесс boundary `run_app`: команды `ctx` (сборка `Ctx` → exit 3 `config_not_found` / exit 2 `invalid_value` / exit 0) и `boom` (exit 1) — эти сценарии через `platform2` в P1 недостижимы, заглушки §7.5 ленивы |
| `hang_cli.py` | харнесс висящей команды `hang`: пишет маркер готовности → спит; тест шлёт SIGINT после маркера → exit 130 без traceback |
| `golden/` | точные снапшоты: `help.txt` (дефолтная ширина 80; перегенерирован в T11 после добавления опции `-h`), `stub_error.txt` (текст ошибки заглушки; они же сверяются с прогонами при `COLUMNS=60/80/120`) |

Golden-снапшоты сгенерированы этим же контуром (`make_env` + `run_platform2`);
при намеренном изменении вывода перегенерируйте их тем же способом и покажите
дифф в ревью.

Цвет/TTY проверяются только в `test_tty.py`: пять условий §12.1
(`NO_COLOR`, `TERM=dumb`, `--no-color`, non-TTY, TTY+`TERM=xterm`) — каждое
по отдельности; патчи внутренних имён v2 запрещены (§10.6) — тесты идут через
entry/hарнессы, без `monkeypatch("apps_platform.cli.<helper>")`.