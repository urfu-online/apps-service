# Установка платформы

Платформа устанавливается одним скриптом. Всё, что нужно — Docker и Bash.

## Требования

- **Docker** (с доступом без `sudo`)
- **Docker Compose Plugin** (`docker compose`, не standalone `docker-compose`)
- **Bash** ≥ 4.0
- **Python** 3.11+ (для Platform CLI)

```bash
# Docker (Ubuntu)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Docker Compose plugin
sudo apt install docker-compose-plugin
```

## Установка

```bash
./install.sh
```

Скрипт задаст три вопроса:

### 1. Тип окружения

| Ввод | Для чего | `project_root` |
|---|---|---|
| `l` — Local | Разработка | Путь к репозиторию |
| `s` — Server | Production VPS | `/apps` |
| `c` — Custom | Свой путь | Вы укажете |

### 2. Путь к сервисам

Где будут лежать сервисы. По умолчанию:
- Local → `./services/` рядом с репозиторием
- Server → `/apps/services/`

### 3. Куда установить CLI

| Вариант | Плюсы | Минусы |
|---|---|---|
| `~/bin` (рекомендуется) | Без sudo, только для вас | Нужно `~/bin` в PATH |
| `/usr/local/bin` | Системно, для всех | Требует sudo |
| Текущая директория | Временный запуск | Нужно вызывать `./ops` |

## Что после установки

Скрипт создаст:

1. **`.ops-config.yml`** — конфиг платформы (tracked в git, серверные значения)
2. **`.ops-config.local.yml`** — ваш локальный override (gitignored, не коммитится)
3. Установит CLI `platform` (опционально, через pipx)

### Проверка

```bash
platform list       # Увидеть все сервисы
```

## Server vs Local

| | Server | Local |
|---|---|---|
| `environment` | `server` | `local` |
| `project_root` | `/apps` | Путь к репозиторию |
| HTTPS | Let's Encrypt (Caddy) | HTTP, `auto_https off` |
| Auth | Keycloak | Built-in (SQLite users) |

> **Важно:** Никогда не коммитьте `.ops-config.local.yml` — он в `.gitignore` специально.
