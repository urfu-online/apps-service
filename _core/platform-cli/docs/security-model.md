# Модель безопасности Platform CLI

> **Версия:** 1.0 · **Дата:** 2026-07-02 · **Аудитория:** разработчики,
> DevOps-инженеры, security-ревьюеры

Этот документ описывает **границы доверия** (trust boundaries) между
компонентами платформы и ключевые риски, которым подвержен `platform-cli`.

---

## 1. Архитектурные границы доверия

```
┌──────────────┐    HTTPS/JWT    ┌──────────────────┐
│   operator   │ ──────────────► │   Master API     │
│ (CLI/dev)    │ ◄────────────── │  (FastAPI)       │
└──────┬───────┘                 └────────┬─────────┘
       │                                  │
       │ docker.sock                      │ docker.sock
       │ (root-equivalent)                │ (root-equivalent)
       ▼                                  ▼
┌──────────────────────────────────────────────────┐
│                  Host Kernel                     │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  │
│  │  Service   │  │  Service   │  │   Caddy    │  │
│  │ Container  │  │ Container  │  │ Container  │  │
│  └────────────┘  └────────────┘  └────────────┘  │
└──────────────────────────────────────────────────┘
```

| Граница | Направление | Защита |
|---------|-------------|--------|
| Operator ↔ Master | HTTPS, JWT | TLS 1.2+, проверка подписи |
| Master ↔ Services | HTTP (internal) | Caddy basic auth, mTLS (planned) |
| CLI ↔ Host | docker.sock | rootless Docker (рекомендуется) |
| Master ↔ Host | docker.sock | изолированный контейнер, capability dropping |

---

## 2. Docker socket — критическая граница доверия

### 2.1. Почему это важно

Монтирование `/var/run/docker.sock` в контейнер (или членство пользователя в
группе `docker`) эквивалентно предоставлению **полного root-доступа к хосту**:

```bash
# Пример атаки через скомпрометированный CLI-контейнер:
docker run -v /:/host -it alpine chroot /host
#  -> получаем shell от root на хосте
```

Возможные действия атакующего:

- Чтение и запись **любых файлов** на хосте (через монтирование `/`).
- Извлечение **секретов** из переменных окружения всех запущенных контейнеров.
- Запуск привилегированных контейнеров с `--cap-add=ALL`.
- Чтение **TLS-сертификатов**, ключей SSH, конфигов Caddy.
- Персистентность — создание контейнера с автозапуском.

### 2.2. Масштаб проблемы

| Сценарий | Риск |
|----------|------|
| CLI запущен от root | Полный компромисс хоста |
| CLI запущен от пользователя из группы `docker` | Полный компромисс хоста |
| CLI в контейнере с `docker.sock` (rw) | Полный компромисс хоста |
| CLI в контейнере с `docker.sock` (ro) | Чтение состояния (частичная компрометация) |
| Rootless Docker (dockerd-rootless) | Изоляция UID/GID, риск минимален |

### 2.3. Рекомендуемая конфигурация

**Безопасный `docker-compose.yml` для CLI:**

```yaml
services:
  platform-cli:
    image: platform-cli:latest
    user: "1000:1000"
    read_only: true
    tmpfs:
      - /tmp
      - /run
    volumes:
      - type: bind
        source: /var/run/docker.sock
        target: /var/run/docker.sock
        read_only: true
    cap_drop: ["ALL"]
    security_opt:
      - "no-new-privileges:true"
    networks:
      - platform
```

**Альтернатива — rootless Docker:**

```bash
# Установка rootless docker
dockerd-rootless-setuptool.sh install

# Запуск CLI под пользователем
systemctl --user start docker
XDG_RUNTIME_DIR=/run/user/$(id -u) platform deploy myservice
```

---

## 3. Аутентификация и авторизация

### 3.1. Master API

- **JWT-токены** с подписью HS256 (ключ `SECRET_KEY`).
- В production: длина `SECRET_KEY` ≥ 32 байт, генерация через
  `openssl rand -hex 32`.
- Поддержка **Keycloak** (OAuth2/OIDC) для SSO.
- Built-in auth: пользователи из `OPS_USERS_FILE` (bcrypt-хэши).

### 3.2. CLI ↔ Master

- Токен хранится в `~/.config/ops-manager/credentials` с правами `0600`.
- Refresh-токен используется для продления сессии (TTL 24 ч).
- `--insecure` отключает TLS-верификацию **только** в dev-режиме
  (`PLATFORM_ENV != production`).

---

## 4. Секреты и переменные окружения

| Источник | Защита |
|----------|--------|
| `.env` в репозитории | Запрещено коммитить, добавлено в `.gitignore` |
| `.env` в `services/<svc>/.env` | Только для compose, права `0600` |
| `docker inspect <container>` | Доступно через docker.sock → ограничить круг лиц |
| `.ops-config.yml` | Секреты должны быть в `secret_refs` (см. ниже) |

**Использование secret_refs** (планируется, шаг 15 P2):

```yaml
# .ops-config.yml
services:
  myapp:
    env:
      DATABASE_URL:
        secret_ref: "vault://prod/db/url"
```

---

## 5. Аудит и логирование

- **Master:** структурированные JSON-логи в stdout, отправка в Loki/ELK.
- **CLI:** `--verbose` включает DEBUG-уровень для диагностики.
- **Caddy:** access-логи с correlation-id, логируются все запросы.
- **Алерты:** изменение конфигурации `SECRET_KEY` → CRITICAL alert.

---

## 6. Известные ограничения

- ❌ Нет rate-limiting на Master API (отложено, см. План Шаг 14).
- ❌ Нет mTLS между Master и сервисами.
- ❌ SQLite без WAL (Шаг 20 P2) — при высокой нагрузке возможны блокировки.
- ⚠️ Catch-all `except Exception` в 11 местах `cli.py` (Шаг 8 P1) — скрытые
  ошибки при backup/deploy/health.

---

## 7. Контрольный список для production-деплоя

- [ ] `SECRET_KEY` сгенерирован через `openssl rand -hex 32`, длина ≥ 32
- [ ] `PLATFORM_ENV=production`
- [ ] `ALLOWED_ORIGINS` содержит конкретные домены (без `*`)
- [ ] `OPS_USERS_FILE` смонтирован в Master с правами `0600`
- [ ] Caddy сконфигурирован с TLS-сертификатами (Let's Encrypt)
- [ ] Docker socket смонтирован `ro` или используется rootless Docker
- [ ] Логи Master отправляются в централизованное хранилище
- [ ] Бэкапы `master.db` и `/etc/ops-manager/` настроены через Kopia
- [ ] Health-check `/healthz` отвечает 200, `/readyz` проверяет зависимости

---

## 8. Сообщение о уязвимостях

Уязвимости принимаются через **security@team.example.com** (PGP key в
`docs/pgp-key.asc`). SLA на первый ответ — 48 часов. Пожалуйста, не создавайте
public issues для security-находок.
