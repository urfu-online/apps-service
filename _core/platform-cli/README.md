# Platform CLI

CLI утилита для управления платформой Platform Master Service.

## Быстрый старт

### Установка через install.sh проекта

При запуске `./install.sh` в корне проекта, вам будет предложено установить Platform CLI:

```bash
cd /apps
./install.sh

# Вам будет задан вопрос:
# Install Platform CLI? [Y/n]: Y
```

### Ручная установка через pipx

```bash
# Установка pipx (если не установлен)
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# Установка platform-cli
pipx install /apps/_core/platform-cli

# Использование
platform --help
platform list
```

### Установка через install.sh скрипт

```bash
cd /apps/_core/platform-cli
./install.sh
```

### Установка через Docker

```bash
docker build -t platform-cli .
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock platform-cli list
```

## Команды

| Команда | Описание |
|---------|----------|
| `platform list` | Показать все сервисы |
| `platform new <name> [public\|internal]` | Создать новый сервис |
| `platform deploy <service>` | Задеплоить сервис |
| `platform deploy <service> --build` | Деплой с пересборкой |
| `platform stop <service>` | Остановить сервис |
| `platform restart <service>` | Перезапустить сервис |
| `platform status [service]` | Показать статус |
| `platform logs <service>` | Просмотр логов |
| `platform logs <service> --follow` | Логи в реальном времени |
| `platform backup <service>` | Создать бэкап |
| `platform reload` | Перезагрузить Caddy |
| `platform info` | Информация о платформе |

## Примеры использования

```bash
# Создать новый публичный сервис
platform new myapp public

# Создать внутренний сервис
platform new internal-api internal

# Задеплоить сервис
platform deploy myapp

# Задеплоить с пересборкой образов
platform deploy myapp --build

# Просмотр статуса всех сервисов
platform status

# Просмотр статуса конкретного сервиса
platform status myapp

# Просмотр логов
platform logs myapp

# Логи в реальном времени
platform logs myapp --follow

# Создать бэкап
platform backup myapp

# Перезагрузить конфигурацию Caddy
platform reload
```

## Структура проекта

```
/apps/_core/platform-cli/
├── apps_platform/
│   ├── __init__.py       # Инициализация пакета
│   ├── api_client.py     # HTTP клиент для Master API
│   ├── caddy_parser.py   # Парсер конфигурации Caddy
│   └── cli.py            # Основной код CLI
├── pyproject.toml        # Конфигурация проекта (PEP 621)
├── Dockerfile            # Для контейнерной версии
├── install.sh            # Скрипт установки через pipx
├── INSTALL.md            # Подробная документация
└── README.md             # Этот файл
```

## Требования

- Python 3.11+
- Docker и Docker Compose
- Доступ к `/var/run/docker.sock`
- Конфигурация `.ops-config.yml`

## Разработка

```bash
# Установка в режиме разработки
pipx install --editable /apps/_core/platform-cli

# Или через pip
pip install -e /apps/_core/platform-cli

# Установка dev зависимостей
pip install -e "/apps/_core/platform-cli[dev]"

# Запуск тестов
pytest

# Линтинг
ruff check apps_platform/
black apps_platform/
```

## Обновление

```bash
# Обновление через pipx
pipx upgrade platform-cli

# Обновление из репозитория
cd /apps/_core/platform-cli
git pull
pipx upgrade platform-cli  # или reinstall
```

## Удаление

```bash
pipx uninstall platform-cli
```

## Интеграция с Ops Manager

После установки через `./install.sh` в корне проекта, `platform` CLI доступен глобально:

```bash
# Оба варианта работают параллельно
ops list              # Bash wrapper (базовые команды)
platform list         # Full CLI (все функции)
```

## Лицензия

MIT
