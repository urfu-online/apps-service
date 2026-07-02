# Platform CLI — Изоляция проекта

## Обзор

Platform CLI полностью изолирован от остальной платформы для обеспечения:
- Независимости от других компонентов
- Чистоты зависимостей
- Безопасности обновлений
- Модульности

## Уровень 1: Изоляция зависимостей (pipx)

### Архитектура

```
~/.local/pipx/venvs/platform-cli/
├── bin/
│   └── platform          # Изолированный исполняемый файл
└── lib/
    └── python3.11/
        └── site-packages/  # Все зависимости изолированы
            ├── typer/
            ├── pyyaml/
            ├── docker/
            ├── requests/
            └── rich/
```

### Преимущества

- ✅ Зависимости не конфликтуют с другими проектами
- ✅ Нет влияния на системный Python
- ✅ Легкое обновление и откат
- ✅ Автоматическое управление виртуальным окружением

### Установка

```bash
pipx install /apps/_core/platform-cli
```

## Уровень 2: Файловая изоляция

### Структура проекта

```
/apps/_core/platform-cli/
├── apps_platform/         # Исходный код (единственное, что нужно)
│   ├── __init__.py
│   └── cli.py
├── pyproject.toml         # Конфигурация PEP 621
├── Dockerfile             # Контейнерная изоляция
├── install.sh             # Скрипт установки
├── README.md
├── INSTALL.md
└── .gitignore
```

### Исключения в .gitignore

Проект игнорирует артефакты сборки:

```
_core/platform-cli/.venv/
_core/platform-cli/venv/
_core/platform-cli/dist/
_core/platform-cli/build/
_core/platform-cli/*.egg-info
```

## Уровень 3: Контейнерная изоляция (Docker)

### Использование

```bash
# Сборка
docker build -t platform-cli /apps/_core/platform-cli

# Запуск
docker run --rm \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v /apps:/apps \
    platform-cli list
```

### Преимущества

- ✅ Полная изоляция от хоста
- ✅ Все зависимости внутри контейнера
- ✅ Кроссплатформенность
- ✅ Воспроизводимость

## Уровень 4: Конфигурационная изоляция

### Независимость от Ops Manager

Platform CLI использует общую конфигурацию, но не зависит от Ops Manager:

```bash
# Конфигурация ищется в:
1. /apps/.ops-config.yml
2. ~/.config/ops-manager/config.yml
```

### Автономная работа

```bash
# CLI работает даже без Ops Manager
platform info          # Показывает информацию
platform list          # Сканирует сервисы напрямую
```

## Сравнение с другими компонентами

| Компонент | Изоляция | Зависимости | Установка |
|-----------|----------|-------------|-----------|
| **platform-cli** | pipx + Docker | Изолированы | `pipx install` |
| master | Docker | Общие | `docker compose up` |
| caddy | Docker | Минимальные | `docker compose up` |
| ops (bash) | Нет | Системные | `install.sh` |

## Миграция с Poetry на pipx

### Было (Poetry)

```bash
cd /apps/_core/platform-cli
poetry install
poetry run platform
```

### Стало (pipx)

```bash
pipx install /apps/_core/platform-cli
platform
```

## Обновление

```bash
# Обновление через pipx
pipx upgrade platform-cli

# Переустановка из репозитория
cd /apps/_core/platform-cli
git pull
pipx upgrade platform-cli
```

## Удаление

```bash
# Полное удаление
pipx uninstall platform-cli

# Очистка всех pipx пакетов
pipx uninstall-all
```

## Безопасность

### Доступ к Docker

Platform CLI требует доступа к Docker socket:

```bash
# Безопасный способ - через группу docker
sudo usermod -aG docker $USER
newgrp docker

# Не рекомендуется - запуск от root
```

### Ограничение прав

В Dockerfile используется непривилегированный пользователь:

```dockerfile
RUN useradd -m -u 1000 platform
USER platform
```

## Диагностика

```bash
# Проверка установки
pipx list

# Проверка пути
which platform

# Проверка версии
platform --version

# Информация о платформе
platform info
```

## Будущие улучшения

1. **Snap package** - для ещё большей изоляции
2. **Homebrew formula** - для macOS
3. **Static binary** - через PyInstaller
4. **Nix package** - для воспроизводимости
