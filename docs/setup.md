# Установка и настройка платформы

Платформа поставляется с автоматизированным скриптом установки `install.sh`, который настраивает окружение, создаёт конфигурацию и устанавливает CLI-утилиту `ops` для управления сервисами.

## Скрипт установки `install.sh`

Скрипт `install.sh` выполняет следующие действия:

1. **Определяет тип окружения**:
   - `local` — для разработки на локальной машине
   - `server` — для развёртывания на VPS/сервере (по умолчанию `/apps`)
   - `custom` — пользовательский путьwhereis

2. **Запрашивает путь к директории `apps`**:
   - По умолчанию: `$SCRIPT_DIR/apps` (для локального) или `/apps` (для сервера)
   - Если директория не существует — предлагает создать

3. **Создаёт конфигурационный файл**:
   - Расположение: `~/.config/ops-manager/config.yml`
   - Содержит:

   ```yaml
   environment: local|server|custom
   apps_root: /путь/к/apps
   project_root: /путь/к/проекту
   core_path: _core
   services_path: services
   docker_host: unix:///var/run/docker.sock
   compose_timeout: 300
   ```

4. **Устанавливает CLI-утилиту `ops`** в одну из директорий:
   - `~/bin` (рекомендуется, не требует sudo)
   - `/usr/local/bin` (системно, требует прав)
   - Текущая директория (временный запуск)

5. **Создаёт исполняемый скрипт `ops`**, который:
   - Загружает конфигурацию
   - Обнаруживает сервисы в `_core` и `services/{public,internal}`
   - Предоставляет команды для управления

## Команды CLI `ops`

После установки доступна команда `ops`:

| Команда              | Описание                                             |
| -------------------- | ---------------------------------------------------- |
| `ops list`           | Показать все найденные сервисы и их статус           |
| `ops up <service>`   | Запустить сервис (через `docker compose up -d`)      |
| `ops down <service>` | Остановить сервис                                    |
| `ops logs <service>` | Просмотр логов в реальном времени (`tail=100`, `-f`) |
| `ops ui`             | Открыть lazydocker для всех сервисов                 |
| `ops ui <service>`   | Открыть lazydocker только для указанного сервиса     |
| `ops reload`         | Перезагрузить конфигурацию Caddy через API           |
| `ops <service>`      | Сокращение: `ops master` = `ops up master`           |

> 💡 Поддерживается автодополнение имён сервисов: если имя совпадает с сервисом — выполняется `up`.

### Примеры

```bash
ops list                    # Посмотреть все сервисы
ops up master               # Запустить master
ops logs caddy              # Логи прокси
ops ui                      # UI для всех сервисов
ops reload                  # Обновить конфиг Caddy после изменений
```

## Конфигурация CLI

Файл: `~/.config/ops-manager/config.yml`

Поля:

- `environment`: тип окружения (`local`, `server`, `custom`)
- `apps_root`: корневая директория с сервисами
- `project_root`: путь к репозиторию (для скриптов)
- `core_path`: поддиректория ядра (по умолчанию `_core`)
- `services_path`: поддиректория сервисов (по умолчанию `services`)
- `docker_host`: путь к Docker socket (поддержка remote Docker)
- `compose_timeout`: таймаут для Docker Compose операций

> ⚠️ Если `~/bin` не в `PATH`, нужно добавить:
>
> ```bash
> echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
> source ~/.bashrc
> ```

## Требования к системе

Перед запуском `install.sh` убедитесь, что установлено:

- **Docker** (с доступом без sudo)
- **Docker Compose Plugin** (не standalone `docker-compose`)
- **Bash** ≥ 4.0
- (Опционально) `lazydocker` — для `ops ui`

### Установка зависимостей (Ubuntu)

```bash
# Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Docker Compose (plugin)
sudo apt install docker-compose-plugin

# lazydocker (UI)
curl https://raw.githubusercontent.com/jesseduffield/lazydocker/master/scripts/install_update_linux.sh | bash
```

> 🔁 После добавления пользователя в группу `docker` — перезагрузите сессию или выполните `newgrp docker`.

## Рекомендации по развёртыванию

### На сервере

1. Склонируйте репозиторий в `/opt/ops-manager` или `/home/user/ops-manager`
2. Запустите:

   ```bash
   ./install.sh
   # Выберите [s] Server production
   # Укажите /apps как apps_root
   ```

3. Все сервисы будут ожидаться в `/apps/services/` и `/apps/_core/`

### На локальной машине

1. Запустите:

   ```bash
   ./install.sh
   # Выберите [l] Local development
   ```

2. Сервисы будут в `./apps/` рядом со скриптом

## Интеграция с CI/CD (опционально)

Можно автоматизировать обновление платформы через GitHub Actions, GitLab CI или cron.

Пример cron-задачи для автообновления:

```bash
# Каждый день в 3:00 — обновить репозиторий и перезапустить master
0 3 * * * cd /opt/ops-manager && git pull && ops down master && ops up master
```
