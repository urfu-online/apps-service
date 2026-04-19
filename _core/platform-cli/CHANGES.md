# Изменения в platform-cli

## Исправленные проблемы

### 1. Dockerfile (КРИТИЧНО)
**Проблема:** Копировалась несуществующая директория `platform/` вместо `apps_platform/`

**Исправление:**
```dockerfile
# Было:
COPY platform/ ./platform/

# Стало:
COPY apps_platform/ ./apps_platform/
```

### 2. Silent fail в backup (КРИТИЧНО)
**Проблема:** Ошибки в команде `backup` не прерывали выполнение, код продолжал работать после ошибок

**Исправление:**
- Добавлены `raise typer.Exit(1)` после всех ошибок
- Успешное завершение теперь возвращает `raise typer.Exit(0)`
- Все сообщения об ошибках изменены с `[yellow]⚠️` на `[red]❌`

**До:**
```python
except requests.exceptions.ConnectionError:
    console.print("[yellow]⚠️ Master Service недоступен...[/yellow]")
# Код продолжал выполняться дальше!
```

**После:**
```python
except requests.exceptions.ConnectionError:
    console.print("[red]❌ Master Service недоступен...[/red]")
    raise typer.Exit(1)  # Прерываем выполнение
```

### 3. Хардкод имени контейнера caddy (СРЕДНЯЯ)
**Проблема:** Имя контейнера `caddy` было захардкожено, не работало с кастомизацией

**Исправление:**
- Добавлен параметр `--container/-c` со значением по умолчанию `caddy`
- Теперь можно указать любое имя контейнера

**Использование:**
```bash
# По умолчанию (контейнер "caddy")
platform reload

# Кастомное имя контейнера
platform reload --container my-caddy
platform reload -c production-caddy
```

## Тестирование

```bash
# Проверка синтаксиса
python -m py_compile apps_platform/cli.py  ✅

# Проверка импорта
python -c "from apps_platform.cli import app"  ✅

# Проверка CLI
python -m apps_platform.cli --help  ✅
python -m apps_platform.cli reload --help  ✅
python -m apps_platform.cli backup --help  ✅
```

## Файлы изменены

1. `/workspace/_core/platform-cli/Dockerfile` - исправлен путь копирования
2. `/workspace/_core/platform-cli/apps_platform/cli.py`:
   - Функция `backup()` - добавлено прерывание при ошибках
   - Функция `reload()` - добавлен параметр `--container`
