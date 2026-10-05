#!/usr/bin/env bash
# =============================================================================
# install-server.sh — установка И аккуратное обновление платформы apps-service
#                     на Ubuntu 22.04 (запуск от root/sudo)
#
# Два режима, определяются автоматически:
#   • ЧИСТАЯ УСТАНОВКА — платформа не развёрнута: полный цикл от создания /apps
#     до тестового сервиса и проверки всех основных функций.
#   • ОБНОВЛЕНИЕ работающей платформы (сервисы продолжают работать) —
#     обнаружен живой стек, требуется явный флаг --upgrade-running:
#       - авто-бэкап master.db, services/, caddy, .env -> /apps/backups/pre-update-<ts>/
#       - git: только `pull --ff-only`. Untracked-файлы (services/, .env, master.db,
#         conf.d) git не трогает НИКОГДА; локальные правки tracked-файлов тоже не
#         удаляются: при конфликте pull завершится ошибкой и мы продолжим с той
#         версией кода, что есть. Никаких reset/checkout/clean.
#       - rsync (--source) без --delete: ничего не удаляет, services/ и master.db
#         исключены из копирования.
#       - core пересобирается БЕЗ `down`: старый master работает на время сборки.
#       - Docker не обновляется (нужен явный --upgrade-docker — это рестарт демона).
#       - smoke-test не разворачивается (нужен явный --with-test-service).
#     Контейнеры сервисов не останавливаются; кратковременный недоступ через Caddy
#     — только на момент пересоздания/перезагрузки caddy (секунды).
#
# Что делает скрипт (по шагам, всё пишется в единый лог-файл):
#   1. Предпроверки (ОС, RAM, диск) + определение режима (установка/обновление)
#   2. Пакеты и Docker + Compose v2 (обновление Docker — только для чистой установки)
#   3. Python 3.11+ (нужен для platform-cli; в 22.04 по умолчанию 3.10)
#   4. Бэкап живого состояния (для обновления) + раскладка/обновление кода в /apps
#   5. ops/platform CLI и системный конфиг (при обновлении уже стоящее не трогаем)
#   6. Сборка и запуск core-сервисов (master + caddy)
#   7. Создание admin-пользователя API (builtin auth)
#   8. Деплой тестового сервиса smoke-test (чистая установка)
#   9. Проверка основных функций платформы
#  10. Диагностика окружения + итоговый отчёт
#
# ЗАПУСК:
#   чистая установка:  sudo bash install-server.sh --domain apps.example.com
#   обновление:        sudo bash install-server.sh --upgrade-running
#
# ОСНОВНЫЕ ОПЦИИ:
#   --domain NAME        PLATFORM_DOMAIN для .env (по умолчанию — из существующего
#                        /apps/.env, иначе localhost)
#   --apps-root PATH     корень установки (по умолчанию /apps)
#   --repo URL           git-репозиторий проекта (по умолчанию origin проекта)
#   --branch NAME        ветка при clone/pull (по умолчанию main)
#   --source DIR         копировать проект из локальной директории вместо git
#   --acme-email EMAIL   e-mail для Let's Encrypt (правит Caddyfile)
#   --upgrade-running    разрешить обновление работающей платформы (с бэкапом)
#   --upgrade-docker     разрешить обновление Docker на живом стеке (рестарт демона)
#   --with-test-service  развернуть smoke-test и на живом стеке
#   --skip-docker        не трогать Docker (только проверить, что работает)
#   --skip-test-service  не разворачивать smoke-test сервис
#   --force              разрешить запуск не на Ubuntu 22.04
#   -h, --help           справка
#
# ЛОГИ:
#   /var/log/apps-platform/install-<дата-время>.log   (ANSI-коды вычищены)
#   Туда пишется ВСЁ: команды, вывод apt/docker/curl, ошибки с номерами строк.
# =============================================================================
set -Eeuo pipefail

# NB: локальные HTTP-проверки (127.0.0.1/localhost) всегда идут с --noproxy '*':
# на сервере с http_proxy/HTTPS_PROXY curl иначе получает 502/503 от прокси
# вместо реального ответа сервиса (проверено на практике). Запросы в интернет
# (docker repo и т.п.) прокси используют штатно.

# ─────────────────────────────────────────────────────────────────────────────
# Глобальные переменные и значения по умолчанию
# ─────────────────────────────────────────────────────────────────────────────
SCRIPT_VERSION="1.1.1"
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"

APPS_ROOT="/apps"
REPO_URL="https://github.com/urfu-online/apps-service.git"
BRANCH="main"
SOURCE_DIR=""
PLATFORM_DOMAIN="${PLATFORM_DOMAIN:-localhost}"
ACME_EMAIL=""
SKIP_DOCKER=false
SKIP_TEST_SERVICE=false
FORCE=false
UPGRADE_RUNNING=false
UPGRADE_DOCKER=false
WITH_TEST_SERVICE=false
LIVE_STACK=false
BACKUP_DIR=""
DOMAIN_EXPLICIT=false
LAST_CMD=""

MASTER_CONTAINER="platform-master"
CADDY_CONTAINER="caddy"
PLATFORM_NETWORK="platform_network"
MASTER_URL="http://127.0.0.1:8001"
CADDY_ADMIN_URL="http://127.0.0.1:2019"
TEST_SERVICE="smoke-test"
TEST_PATH="/smoke-test"
TEST_MARKER="SMOKE_TEST_OK"

LOG_DIR="/var/log/apps-platform"
LOG_FILE=""
PY_BIN=""
SHIM_DIR=""
ADMIN_UID=""
ADMIN_PASSWORD=""
BOOTSTRAP_STARTED_AT=$(date +%s)

PASS_N=0; FAIL_N=0; WARN_N=0
declare -a RESULTS=()
STEP="(инициализация)"

# ─────────────────────────────────────────────────────────────────────────────
# Оформление
# ─────────────────────────────────────────────────────────────────────────────
if [ -t 1 ]; then
    R=$'\033[0;31m'; G=$'\033[0;32m'; Y=$'\033[1;33m'; B=$'\033[0;34m'
    C=$'\033[0;36m'; D=$'\033[2m'; N=$'\033[0m'
else
    R=""; G=""; Y=""; B=""; C=""; D=""; N=""
fi

ts()     { date '+%F %T'; }
log()    { echo -e "[$(ts)] ${B}ℹ️  $*${N}"; }
ok()     { echo -e "[$(ts)] ${G}✅ $*${N}"; }
warn()   { echo -e "[$(ts)] ${Y}⚠️  $*${N}"; }
err()    { echo -e "[$(ts)] ${R}❌ $*${N}" >&2; }
hint()   { echo -e "[$(ts)] ${Y}→ $*${N}"; }
section(){ echo -e "\n${C}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${N}"; \
           echo -e "${C}▶ $*${N}"; \
           echo -e "${C}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${N}"; }
# Завершение по явному решению (не ошибка): снимаем ERR-ловушку, чтобы она
# не срабатывала на самом `exit`.
finish() { trap - ERR; exit "${1:-0}"; }
die()    { err "$*"; err "Лог: ${LOG_FILE:-<лог ещё не открыт>}"; finish 1; }

# Выполняет команду, показывая её перед запуском (идёт и в консоль, и в лог).
run() {
    echo -e "[$(ts)] ${D}+ $*${N}"
    LAST_CMD="$*"
    "$@"
}

# ─────────────────────────────────────────────────────────────────────────────
# Учёт проверок (PASS/FAIL/WARN) для итогового отчёта
# ─────────────────────────────────────────────────────────────────────────────
res() { # $1 = PASS|FAIL|WARN, $2 = название, $3 = детали
    RESULTS+=("$1|$2|${3:-}")
    case "$1" in
        PASS) PASS_N=$((PASS_N + 1)); ok "$2${3:+ — $3}" ;;
        FAIL) FAIL_N=$((FAIL_N + 1)); err "$2${3:+ — $3}" ;;
        WARN) WARN_N=$((WARN_N + 1)); warn "$2${3:+ — $3}" ;;
    esac
}

expect() { # $1 = название, $2 = детали при успехе, $3... = команда
    local name="$1" detail="$2"; shift 2
    local out rc=0
    out=$("$@" 2>&1) || rc=$?
    if [ "$rc" -eq 0 ]; then
        res PASS "$name" "$detail"
    else
        res FAIL "$name" "exit=$rc: $(echo "$out" | tail -3 | tr '\n' ' ' | cut -c1-300)"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Обработчики ошибок и выхода
# ─────────────────────────────────────────────────────────────────────────────
on_err() {
    local rc="$1" line="$2" cmd="$3"
    # Внутри run() BASH_COMMAND == "$@" — подставляем реальную команду.
    [ "$cmd" = '"$@"' ] && cmd="${LAST_CMD:-$cmd}"
    echo "" >&2
    err "СБОЙ ВЫПОЛНЕНИЯ (exit=$rc) на строке ${line}: ${cmd}"
    err "Шаг: $STEP"
    err "Полный лог: ${LOG_FILE:-<лог не открыт>}"
    hint "docker logs -f $MASTER_CONTAINER --tail 100"
    hint "tail -f $APPS_ROOT/_core/caddy/logs/debug.log"
}

on_exit() {
    local rc=$?
    rm -rf "${SHIM_DIR:-}" 2>/dev/null || true
    if [ "$rc" -ne 0 ]; then
        echo "" >&2
        err "Скрипт завершился с ошибкой (exit=$rc) на шаге: $STEP"
        [ -n "$LOG_FILE" ] && err "Лог: $LOG_FILE"
    fi
}

trap 'on_err $? $LINENO "$BASH_COMMAND"' ERR
trap on_exit EXIT

# ─────────────────────────────────────────────────────────────────────────────
# Аргументы командной строки
# ─────────────────────────────────────────────────────────────────────────────
usage() {
    awk 'NR==1{next} /^# =+$/{if(seen++){exit}} /^#/{sub(/^# ?/,""); print}' "$SCRIPT_PATH"
    exit 0
}

while [ $# -gt 0 ]; do
    case "$1" in
        --apps-root)      APPS_ROOT="$2"; shift 2 ;;
        --repo)           REPO_URL="$2"; shift 2 ;;
        --branch)         BRANCH="$2"; shift 2 ;;
        --source)         SOURCE_DIR="$2"; shift 2 ;;
        --domain)         PLATFORM_DOMAIN="$2"; DOMAIN_EXPLICIT=true; shift 2 ;;
        --acme-email)     ACME_EMAIL="$2"; shift 2 ;;
        --upgrade-running) UPGRADE_RUNNING=true; shift ;;
        --upgrade-docker) UPGRADE_DOCKER=true; shift ;;
        --with-test-service) WITH_TEST_SERVICE=true; shift ;;
        --skip-docker)    SKIP_DOCKER=true; shift ;;
        --skip-test-service) SKIP_TEST_SERVICE=true; shift ;;
        --force)          FORCE=true; shift ;;
        -h|--help)        usage ;;
        *)                die "Неизвестный аргумент: $1 (смотрите --help)" ;;
    esac
done

# Если скрипт запущен из копии проекта (рядом _core/master) — используем её
# как источник по умолчанию, чтобы не требовать git-доступа.
if [ -z "$SOURCE_DIR" ] && [ -f "$SCRIPT_DIR/_core/master/docker-compose.yml" ]; then
    SOURCE_DIR="$SCRIPT_DIR"
fi

# Самоперезапуск под sudo, если запустили не от root.
if [ "$EUID" -ne 0 ]; then
    warn "Требуются права root. Перезапуск через sudo..."
    exec sudo -- bash "$SCRIPT_PATH" "$@"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Инициализация логирования: всё пишется в консоль И в лог-файл
# ─────────────────────────────────────────────────────────────────────────────
umask 022
mkdir -p "$LOG_DIR"
chmod 0700 "$LOG_DIR"
LOG_FILE="$LOG_DIR/install-$(date +%Y%m%d-%H%M%S).log"
touch "$LOG_FILE"
chmod 0600 "$LOG_FILE"

# Лог всегда без ANSI-кодов (удобно grep/less), консоль — с цветом.
strip_ansi() { sed -u $'s/\033\\[[0-9;]*m//g'; }
exec > >(tee >(strip_ansi >> "$LOG_FILE")) 2>&1

TMP_DIR=$(mktemp -d /tmp/install-server.XXXXXX)

# Домен: если не задан явно через --domain — берём из существующего .env платформы.
# При обновлении работающей установки её домен меняться не должен (в т.ч.
# apps.openedu.urfu.ru и подобные).
DOMAIN_SOURCE="по умолчанию/из опций"
if ! $DOMAIN_EXPLICIT && [ -f "$APPS_ROOT/.env" ]; then
    EXISTING_DOMAIN=$(grep '^PLATFORM_DOMAIN=' "$APPS_ROOT/.env" | tail -1 | cut -d= -f2- | tr -d ' "')
    if [ -n "$EXISTING_DOMAIN" ]; then
        PLATFORM_DOMAIN="$EXISTING_DOMAIN"
        DOMAIN_SOURCE="из существующего $APPS_ROOT/.env"
    fi
fi

log "Лог-файл: $LOG_FILE"
log "Версия скрипта: $SCRIPT_VERSION | root: $APPS_ROOT | domain: $PLATFORM_DOMAIN ($DOMAIN_SOURCE)"

# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ─────────────────────────────────────────────────────────────────────────────
http_code() { # $1 = url, печатает HTTP-код (000 при недоступности)
    local out
    out=$(curl -s --noproxy '*' -o /dev/null -w '%{http_code}' -m 10 "$1" 2>/dev/null) || true
    echo "${out:-000}"
}

dump_diagnostics() {
    echo ""
    echo -e "${C}┌─ ДИАГНОСТИКА ОКРУЖЕНИЯ (для отладки) ─────────────────────────────${N}"
    echo -e "${C}│${N} docker ps -a:"
    docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>&1 | sed "s/^/${C}│${N}   /"
    for c in "$MASTER_CONTAINER" "$CADDY_CONTAINER" "$TEST_SERVICE"; do
        if docker inspect "$c" >/dev/null 2>&1; then
            echo -e "${C}│${N} $c: $(docker inspect -f 'status={{.State.Status}} exit={{.State.ExitCode}} restarts={{.RestartCount}} oom={{.State.OOMKilled}}' "$c" 2>/dev/null)"
        fi
    done
    echo -e "${C}│${N} docker logs $MASTER_CONTAINER (tail 60):"
    docker logs --tail 60 "$MASTER_CONTAINER" 2>&1 | sed "s/^/${C}│${N}   [master] /"
    echo -e "${C}│${N} docker logs $CADDY_CONTAINER (tail 20):"
    docker logs --tail 20 "$CADDY_CONTAINER" 2>&1 | sed "s/^/${C}│${N}   [caddy] /"
    if [ -d "$APPS_ROOT/_core/caddy/conf.d" ]; then
        echo -e "${C}│${N} Caddy conf.d:"
        ls -la "$APPS_ROOT/_core/caddy/conf.d" 2>&1 | sed "s/^/${C}│${N}   /"
    fi
    echo -e "${C}└────────────────────────────────────────────────────────────────────${N}"
}

wait_http() { # $1 = url, $2 = timeout сек, $3 = ожидаемый код (по умолчанию 2xx)
    local url="$1" timeout="${2:-120}" want="${3:-2}" start code
    start=$(date +%s)
    while true; do
        code=$(http_code "$url")
        case "$code" in
            ${want}*) return 0 ;;
        esac
        if [ $(( $(date +%s) - start )) -ge "$timeout" ]; then
            echo "тайм-аут ${timeout}s, последний HTTP-код: $code"
            return 1
        fi
        sleep 3
    done
}

# Определяет, развёрнута ли уже платформа (живой стек с данными/сервисами).
# Критерии: непустой master.db (там есть схема/пользователи), либо сервисы в
# services/ (кроме служебного smoke-test), либо работающие core-контейнеры при
# наличии хоть одного сервиса. Пустая неудачная попытка установки НЕ считается
# живым стеком — повторный запуск пройдёт как чистая установка.
detect_live_stack() {
    LIVE_STACK=false
    local why="" svc_total=0 svc_real=0
    if [ -d "$APPS_ROOT/services" ]; then
        svc_total=$(find "$APPS_ROOT/services" -mindepth 3 -maxdepth 3 -name service.yml 2>/dev/null | wc -l)
        svc_real=$(find "$APPS_ROOT/services" -mindepth 3 -maxdepth 3 -name service.yml 2>/dev/null | grep -vc "/$TEST_SERVICE/" || true)
    fi
    local core_running=false
    if command -v docker >/dev/null 2>&1; then
        for c in "$MASTER_CONTAINER" "$CADDY_CONTAINER"; do
            if [ "$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null)" = "true" ]; then
                core_running=true
                break
            fi
        done
    fi

    if [ "$svc_real" -gt 0 ]; then
        LIVE_STACK=true; why="в services/ есть сервисы: $svc_real"
    elif [ -s "$APPS_ROOT/_core/master/master.db" ]; then
        LIVE_STACK=true; why="master.db содержит данные ($APPS_ROOT/_core/master/master.db)"
    elif $core_running && [ "$svc_total" -gt 0 ]; then
        LIVE_STACK=true; why="core-контейнеры работают + $svc_total сервис(ов)"
    fi

    if $LIVE_STACK; then
        log "Режим: ОБНОВЛЕНИЕ работающей платформы — $why"
    else
        log "Режим: ЧИСТАЯ УСТАНОВКА"
    fi
}

# Бэкап живого состояния перед любыми изменениями кода/конфигов.
# Данные сервисов (postgres/data и т.п.) не архивируем — как update-platform.sh.
backup_live_state() {
    BACKUP_DIR="$APPS_ROOT/backups/pre-update-$(date +%Y%m%d-%H%M%S)"
    run mkdir -p "$BACKUP_DIR"
    run chmod 0750 "$BACKUP_DIR"
    if [ -s "$APPS_ROOT/_core/master/master.db" ]; then
        run cp -a "$APPS_ROOT/_core/master/master.db" "$BACKUP_DIR/master.db"
    fi
    if [ -d "$APPS_ROOT/services" ]; then
        run tar -C "$APPS_ROOT" --exclude='*/postgres/data' --exclude='*/node_modules' \
            --exclude='*.log' -czf "$BACKUP_DIR/services.tgz" services
    fi
    if [ -d "$APPS_ROOT/_core/caddy" ]; then
        run tar -C "$APPS_ROOT" -czf "$BACKUP_DIR/caddy-config.tgz" \
            _core/caddy/conf.d _core/caddy/Caddyfile _core/caddy/snippets 2>/dev/null \
            || warn "caddy-config.tgz не собран полностью (часть путей отсутствует)"
    fi
    [ -f "$APPS_ROOT/.env" ] && run cp -a "$APPS_ROOT/.env" "$BACKUP_DIR/.env"
    [ -f "$APPS_ROOT/.ops-config.yml" ] && run cp -a "$APPS_ROOT/.ops-config.yml" "$BACKUP_DIR/.ops-config.yml"
    ok "Бэкап живого состояния: $BACKUP_DIR ($(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1))"
    hint "Откат: восстановить master.db/services/caddy из $BACKUP_DIR и выполнить restart_core.sh"
}

# ─────────────────────────────────────────────────────────────────────────────
# ШАГ 1. Предпроверки
# ─────────────────────────────────────────────────────────────────────────────
section "ШАГ 1/10. Предпроверки системы"
STEP="Шаг 1: предпроверки"

if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    log "ОС: ${PRETTY_NAME:-$ID $VERSION_ID} ($(uname -m), $(uname -r))"
    if [ "${ID:-}" != "ubuntu" ]; then
        if $FORCE; then
            warn "ОС не Ubuntu (${ID:-unknown}) — продолжаем из-за --force"
        else
            die "Ожидается Ubuntu 22.04. Найдено: ${PRETTY_NAME:-$ID}. Используйте --force на свой страх и риск."
        fi
    elif [ "${VERSION_ID:-}" != "22.04" ]; then
        warn "Скрипт тестировался на Ubuntu 22.04, найдено ${VERSION_ID:-?} — продолжаем"
    else
        ok "Ubuntu 22.04 LTS подтверждена"
    fi
else
    warn "/etc/os-release не найден — проверка ОС пропущена"
fi

command -v apt-get >/dev/null 2>&1 || die "Не найден apt-get — нужен Ubuntu/Debian"
command -v systemctl >/dev/null 2>&1 || die "Не найден systemctl — нужна systemd"

MEM_KB=$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)
if [ "$MEM_KB" -lt 3600000 ]; then
    warn "ОЗУ меньше 4 ГБ ($((MEM_KB / 1024)) МБ) — платформе рекомендуется минимум 4 ГБ"
else
    ok "ОЗУ: $((MEM_KB / 1024 / 1024)) ГБ"
fi

DISK_AVAIL=$(df -Pm "$(dirname "$APPS_ROOT")" 2>/dev/null | awk 'NR==2 {print $4}')
if [ -n "${DISK_AVAIL:-}" ] && [ "$DISK_AVAIL" -lt 10240 ]; then
    warn "Свободно ${DISK_AVAIL} МБ — рекомендуется минимум 10 ГБ"
else
    ok "Диск: свободно ${DISK_AVAIL:-?} МБ"
fi

if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    log "Запуск от пользователя: $SUDO_USER (через sudo)"
else
    log "Запуск напрямую от root"
fi

# --- Определение режима и защита живого стека ---
detect_live_stack

if $LIVE_STACK && ! $UPGRADE_RUNNING; then
    echo "" >&2
    err "Обнаружена УЖЕ работающая платформа в $APPS_ROOT — без явного подтверждения не трогаю."
    hint "Аккуратное обновление (бэкап, без остановки сервисов, без обновления Docker):"
    hint "  sudo bash $SCRIPT_PATH --upgrade-running [--domain $PLATFORM_DOMAIN]"
    hint "Чистая установка — только на чистый сервер (или удалите $APPS_ROOT осознанно)."
    die "Запуск остановлен: требуется --upgrade-running"
fi

if $LIVE_STACK; then
    log "Политика обновления: бэкап перед изменениями; core без down; Docker не трогаем; smoke-test пропускаем"
    if ! $SKIP_TEST_SERVICE && ! $WITH_TEST_SERVICE; then
        SKIP_TEST_SERVICE=true
        log "smoke-test пропущен (живой стек). Для проверки маршрута: --with-test-service"
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# ШАГ 2. Системные пакеты и Docker
# ─────────────────────────────────────────────────────────────────────────────
section "ШАГ 2/10. Системные пакеты и Docker"
STEP="Шаг 2: пакеты и Docker"

export DEBIAN_FRONTEND=noninteractive
run apt-get update -y
run apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg lsb-release apt-transport-https \
    git jq rsync openssl sqlite3 \
    python3 python3-pip python3-venv

if ! curl -fsI -m 15 https://download.docker.com/linux/ubuntu/gpg >/dev/null 2>&1; then
    die "Нет доступа к download.docker.com — проверьте интернет/прокси на сервере"
fi
ok "Доступ в интернет подтверждён"

if $SKIP_DOCKER; then
    warn "--skip-docker: установка/обновление Docker пропущена"
elif $LIVE_STACK && ! $UPGRADE_DOCKER; then
    log "Живой стек: Docker не обновляется (для обновления нужен --upgrade-docker — это рестарт демона)"
    if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
        die "Живой стек заявлен, но Docker-демон недоступен — проверьте установку Docker"
    fi
    if ! docker compose version >/dev/null 2>&1; then
        warn "Docker Compose v2 (plugin) не найден — запустите с --upgrade-docker или установите docker-compose-plugin"
    fi
else
    DOCKER_WAS_RUNNING=false
    if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
        DOCKER_WAS_RUNNING=true
        log "Docker уже установлен: $(docker --version 2>/dev/null)"
        EXISTING=$(docker ps -q 2>/dev/null | wc -l)
        if [ "$EXISTING" -gt 0 ]; then
            warn "На сервере уже запущено контейнеров: $EXISTING — Docker будет обновлён (контейнеры не удаляются, возможен кратковременный рестарт демона)"
        fi
    fi

    # Конфликтующие пакеты (докер из Ubuntu-репозитория) убираем, как в официальной
    # инструкции Docker. Пакет docker-ce ставится из официального репо.
    if ! dpkg -s docker-ce >/dev/null 2>&1; then
        for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
            if dpkg -s "$pkg" >/dev/null 2>&1; then
                log "Удаление конфликтующего пакета: $pkg"
                run apt-get remove -y "$pkg"
            fi
        done
    fi

    CODENAME=$(. /etc/os-release && echo "${VERSION_CODENAME:-jammy}")
    ARCH=$(dpkg --print-architecture)
    log "Docker apt-репозиторий: $CODENAME / $ARCH"

    run install -m 0755 -d /etc/apt/keyrings
    run curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    run chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${CODENAME} stable" \
        > /etc/apt/sources.list.d/docker.list
    run apt-get update -y
    run apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    run systemctl enable docker
    if $DOCKER_WAS_RUNNING; then
        run systemctl restart docker
    else
        run systemctl start docker
    fi
fi

# Проверки Docker
expect "Демон Docker отвечает" "$(docker --version 2>/dev/null)" docker info
expect "Docker Compose v2 (plugin)" "$(docker compose version 2>/dev/null)" docker compose version
if dpkg -s docker-ce >/dev/null 2>&1; then
    res PASS "Docker из официального репозитория" "$(dpkg-query -W -f='${Version}' docker-ce 2>/dev/null)"
else
    res WARN "Docker не из официального репозитория (docker-ce)" "версия: $(docker --version 2>/dev/null || echo 'нет')"
fi

# Группа platform-admins (права на docker.sock, используется install.sh и CLI)
if ! getent group platform-admins >/dev/null 2>&1; then
    run groupadd platform-admins
    ok "Создана группа platform-admins"
else
    ok "Группа platform-admins уже существует"
fi
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    if id -nG "$SUDO_USER" | grep -qw platform-admins; then
        ok "Пользователь $SUDO_USER уже в группе platform-admins"
    else
        run usermod -aG platform-admins "$SUDO_USER"
        warn "Пользователь $SUDO_USER добавлен в platform-admins — нужен перелогин для работы без sudo"
    fi
fi

# Внешняя docker-сеть, на которой живут master/caddy/сервисы
if docker network inspect "$PLATFORM_NETWORK" >/dev/null 2>&1; then
    ok "Docker-сеть $PLATFORM_NETWORK существует"
else
    run docker network create "$PLATFORM_NETWORK"
    ok "Создана docker-сеть $PLATFORM_NETWORK"
fi

# ─────────────────────────────────────────────────────────────────────────────
# ШАГ 3. Python 3.11+ (нужен для platform-cli)
# ─────────────────────────────────────────────────────────────────────────────
section "ШАГ 3/10. Python 3.11+ для platform-cli"
STEP="Шаг 3: Python 3.11+"

# Ubuntu 22.04 по умолчанию даёт python3.10, а platform-cli требует >=3.11.
detect_python() {
    local cand ver major minor
    for cand in python3.13 python3.12 python3.11 python3; do
        if command -v "$cand" >/dev/null 2>&1; then
            ver=$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "0.0")
            major=${ver%%.*}; minor=${ver##*.}
            if [ "$major" -gt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -ge 11 ]; }; then
                PY_BIN=$(command -v "$cand")
                return 0
            fi
        fi
    done
    return 1
}

if detect_python; then
    ok "Подходит системный Python: $PY_BIN ($("$PY_BIN" --version))"
else
    log "Python 3.11+ не найден — пробуем установить из apt..."
    if ! run apt-get install -y python3.11 python3.11-venv; then
        warn "Пакет python3.11 недоступен в репозиториях — добавляем PPA deadsnakes"
        run apt-get install -y software-properties-common
        run add-apt-repository -y ppa:deadsnakes/ppa
        run apt-get update -y
        run apt-get install -y python3.12 python3.12-venv
    fi
    detect_python || die "Не удалось установить Python 3.11+. Установите вручную (deadsnakes PPA) и перезапустите скрипт."
    ok "Установлен Python: $PY_BIN ($("$PY_BIN" --version))"
fi

if ! "$PY_BIN" -m pip --version >/dev/null 2>&1; then
    log "pip для $PY_BIN не найден — поднимаем через ensurepip"
    run "$PY_BIN" -m ensurepip --upgrade
fi

# PEP 668 (Ubuntu 24.04+): системный Python помечен EXTERNALLY-MANAGED и pip
# отказывается ставить пакеты в системное окружение. Наши операции этому не
# противоречат — ставим только в /opt/pipx (--target), но для совместимости
# добавляем --break-system-packages лишь когда маркер действительно есть
# (на 22.04 флаг неизвестен старому pip, а маркера нет — ничего не добавляем).
PIP_FLAGS=()
PY_STDLIB=$("$PY_BIN" -c 'import sysconfig; print(sysconfig.get_path("stdlib"))' 2>/dev/null || echo "")
if [ -n "$PY_STDLIB" ] && [ -f "$PY_STDLIB/EXTERNALLY-MANAGED" ]; then
    PIP_FLAGS+=(--break-system-packages)
    log "Python помечен externally-managed (PEP 668) — pip-операции с --break-system-packages (установка только в /opt/pipx)"
fi
run "$PY_BIN" -m pip install "${PIP_FLAGS[@]}" --quiet --upgrade pip setuptools wheel
ok "pip: $("$PY_BIN" -m pip --version 2>/dev/null | head -1)"

# Готовим pipx «приколотый» к нужному интерпретатору: штатный install.sh
# platform-cli использует `python3`/`pipx`, а системный python3 на 22.04 — 3.10.
log "Подготовка изолированного pipx (/opt/pipx) под $PY_BIN"
run install -d -m 0755 /opt/pipx/bin /opt/pipx/venvs
run "$PY_BIN" -m pip install "${PIP_FLAGS[@]}" --quiet --target /opt/pipx/pipx-installer pipx
cat > /opt/pipx/bin/pipx <<PIPX_EOF
#!/bin/bash
# Managed by install-server.sh — pipx, закреплённый на Python $PY_BIN.
export PIPX_HOME="/opt/pipx"
export PIPX_BIN_DIR="/usr/local/bin"
export PYTHONPATH="/opt/pipx/pipx-installer\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$PY_BIN" -m pipx "\$@"
PIPX_EOF
chmod 0755 /opt/pipx/bin/pipx

# Директория-шим: внутри неё python3 -> $PY_BIN, pipx -> наш wrapper.
# Подсовывается в PATH только на время вызова install.sh проекта.
SHIM_DIR=$(mktemp -d /tmp/install-shim.XXXXXX)
ln -sf "$PY_BIN" "$SHIM_DIR/python3"
ln -sf /opt/pipx/bin/pipx "$SHIM_DIR/pipx"
ok "Шим PATH подготовлен: $SHIM_DIR"

# ─────────────────────────────────────────────────────────────────────────────
# ШАГ 4. Раскладка проекта в $APPS_ROOT
# ─────────────────────────────────────────────────────────────────────────────
section "ШАГ 4/10. Раскладка проекта в $APPS_ROOT"
STEP="Шаг 4: копирование проекта"

# Бэкап живого состояния — до любых изменений кода/конфигов.
if $LIVE_STACK; then
    backup_live_state
fi

run mkdir -p "$APPS_ROOT"

if [ -f "$APPS_ROOT/_core/master/docker-compose.yml" ] && [ -z "$SOURCE_DIR" ]; then
    log "Проект уже присутствует в $APPS_ROOT — обновление через git pull"
    if [ -d "$APPS_ROOT/.git" ]; then
        LOCAL_CHANGES=$(git -C "$APPS_ROOT" status --short 2>/dev/null | head -20)
        if [ -n "$LOCAL_CHANGES" ]; then
            warn "В рабочем дереве есть локальные изменения/незакоммиченные файлы — git их НЕ трогает:"
            echo "$LOCAL_CHANGES" | sed 's/^/    | /'
        else
            ok "Рабочее дерево чистое (локальных правок нет)"
        fi
        # pull --ff-only безопасен: untracked-файлы (services/, .env, master.db, conf.d)
        # не удаляются никогда; при локальных правках tracked-файлов pull откажется
        # мержить и мы продолжим с текущим кодом. Никаких reset/checkout/clean.
        log "git pull --ff-only origin $BRANCH (ничего не удаляет; при конфликте — продолжим с текущим кодом)"
        if ! run git -C "$APPS_ROOT" pull --ff-only origin "$BRANCH"; then
            warn "git pull не удался (локальные изменения или расходящаяся история) — продолжаем с той версией, что есть в $APPS_ROOT"
        fi
        log "Код после обновления: $(git -C "$APPS_ROOT" log -1 --oneline 2>/dev/null || echo '?')"
    else
        warn "Каталог $APPS_ROOT без .git — автообновление пропущено"
    fi
elif [ -n "$SOURCE_DIR" ]; then
    SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd)"
    [ -f "$SOURCE_DIR/_core/master/docker-compose.yml" ] \
        || die "--source: в $SOURCE_DIR нет _core/master/docker-compose.yml"
    if [ "$SOURCE_DIR" = "$(cd "$APPS_ROOT" && pwd)" ]; then
        log "Источник совпадает с $APPS_ROOT — копирование не требуется"
    else
        log "Копирование проекта из $SOURCE_DIR -> $APPS_ROOT (rsync, services/ не трогаем)"
        run rsync -a \
            --exclude '__pycache__' \
            --exclude '*.pyc' \
            --exclude '.venv' \
            --exclude 'venv' \
            --exclude 'node_modules' \
            --exclude '.pytest_cache' \
            --exclude '.ruff_cache' \
            --exclude '.mypy_cache' \
            --exclude 'master.db' \
            --exclude 'site' \
            --exclude 'services' \
            --exclude 'logs/*.log' \
            --exclude '.ops-config.local.yml' \
            "$SOURCE_DIR/" "$APPS_ROOT/"
    fi
else
    if [ -e "$APPS_ROOT/_core" ]; then
        die "$APPS_ROOT уже содержит _core — укажите --source или запустите в пустой каталог"
    fi
    log "git clone $REPO_URL (ветка $BRANCH) -> $APPS_ROOT"
    if ! run git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$APPS_ROOT"; then
        die "git clone не удался. Варианты: указать --repo <url> с доступом, либо скопировать проект на сервер и запустить с --source <dir>"
    fi
fi

[ -f "$APPS_ROOT/_core/master/docker-compose.yml" ] \
    || die "После развёртывания в $APPS_ROOT нет _core/master/docker-compose.yml — структура проекта повреждена"
ok "Исходники проекта на месте: $APPS_ROOT"
if [ -d "$APPS_ROOT/.git" ]; then
    log "Развёрнутый код: $(git -C "$APPS_ROOT" log -1 --oneline 2>/dev/null || echo '<git недоступен>')"
fi

# --- Runtime-структура (в git не хранится) ---
log "Создание runtime-каталогов и артефактов"
run mkdir -p \
    "$APPS_ROOT/services/public" \
    "$APPS_ROOT/services/internal" \
    "$APPS_ROOT/_core/caddy/conf.d" \
    "$APPS_ROOT/_core/caddy/data" \
    "$APPS_ROOT/_core/caddy/config" \
    "$APPS_ROOT/_core/caddy/sites" \
    "$APPS_ROOT/_core/caddy/logs/services" \
    "$APPS_ROOT/backups/backups" \
    "$APPS_ROOT/logs"

# master.db должен быть ФАЙЛОМ: если Docker-маунту достаётся директория —
# SQLite не поднимется. Такие случаи уже встречались — аккуратно убираем в сторону.
if [ -d "$APPS_ROOT/_core/master/master.db" ]; then
    warn "Обнаружен КАТАЛОГ _core/master/master.db (артефакт docker volume) — убираю в сторону"
    run mv "$APPS_ROOT/_core/master/master.db" "$APPS_ROOT/_core/master/master.db.dir-$(date +%s)"
fi
run touch "$APPS_ROOT/_core/master/master.db"

# Маркер корня проекта (по нему CLI резолвит корень из любой директории)
run touch "$APPS_ROOT/.ops-root"

# --- .env (в git не хранится) ---
ENV_FILE="$APPS_ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
    SECRET_KEY=$(openssl rand -hex 32)
    cat > "$ENV_FILE" <<ENV_EOF
# Generated by install-server.sh $(date -u +%FT%TZ)
APP_ENV=prod
PLATFORM_DOMAIN=${PLATFORM_DOMAIN}
SECRET_KEY=${SECRET_KEY}
ENV_EOF
    chmod 0600 "$ENV_FILE"
    ok "Создан $ENV_FILE (APP_ENV=prod, PLATFORM_DOMAIN=$PLATFORM_DOMAIN, SECRET_KEY сгенерирован)"
else
    warn "$ENV_FILE уже существует — не перезаписываю"
    grep -q '^PLATFORM_DOMAIN=' "$ENV_FILE" || warn "В $ENV_FILE нет PLATFORM_DOMAIN — добавьте вручную"
fi

if [ -n "$ACME_EMAIL" ]; then
    log "Установка ACME e-mail в Caddyfile: $ACME_EMAIL"
    run sed -i "s/^\\s*email .*/\\temail $ACME_EMAIL/" "$APPS_ROOT/_core/caddy/Caddyfile"
fi

# ─────────────────────────────────────────────────────────────────────────────
# ШАГ 5. install.sh: ops, platform CLI, системный конфиг
# ─────────────────────────────────────────────────────────────────────────────
section "ШАГ 5/10. Установка CLI (ops + platform) и системного конфига"
STEP="Шаг 5: install.sh (ops/platform)"

# Отвечаем на интерактивные вопросы install.sh заранее, в строгом порядке:
#   1) тип окружения: s (server)      -> корень /apps
#   2) путь корня:    $APPS_ROOT
#   3) куда ставить ops: 2 (/usr/local/bin)
#   4) Platform CLI: Y (да)
if $LIVE_STACK && [ -f /etc/ops-manager/config.yml ] && [ -x /usr/local/bin/ops ] && command -v platform >/dev/null 2>&1; then
    log "Обновление: ops/platform и системный конфиг уже установлены — install.sh пропущен"
    log "(не перетирает настройки и не рестартует docker.socket на живом стеке)"
else
    if ! (
        cd "$APPS_ROOT"
        export PATH="$SHIM_DIR:$PATH"
        printf 's\n%s\n2\nY\n' "$APPS_ROOT" | bash ./install.sh
    ); then
        die "install.sh завершился с ошибкой — см. вывод выше и лог"
    fi
fi

# install.sh не использует set -e — проверяем фактический результат
if [ -f /etc/ops-manager/config.yml ]; then
    res PASS "Системный конфиг /etc/ops-manager/config.yml" "$(grep '^project_root' /etc/ops-manager/config.yml | tr -d ' ')"
else
    res FAIL "Системный конфиг /etc/ops-manager/config.yml" "файл не создан"
fi
if [ -x /usr/local/bin/ops ]; then
    res PASS "Команда ops установлена" "/usr/local/bin/ops"
else
    res FAIL "Команда ops установлена" "/usr/local/bin/ops не найден"
fi

if ! command -v platform >/dev/null 2>&1; then
    warn "platform CLI не появился после install.sh — ставим напрямую через pipx"
    (
        export PIPX_HOME=/opt/pipx PIPX_BIN_DIR=/usr/local/bin
        run /opt/pipx/bin/pipx install --force "$APPS_ROOT/_core/platform-cli"
    ) || true
    [ -x /opt/pipx/venvs/platform-cli/bin/platform ] \
        && ln -sf /opt/pipx/venvs/platform-cli/bin/platform /usr/local/bin/platform
fi

if command -v platform >/dev/null 2>&1; then
    res PASS "platform CLI установлен" "$(readlink -f "$(command -v platform)")"
    # Проверяем, что CLI стартует и видит корень проекта
    if OUT=$(platform list 2>&1); then
        res PASS "platform list работает" "$(echo "$OUT" | head -3 | tr '\n' ' ' | cut -c1-160)"
    else
        res FAIL "platform list работает" "$(echo "$OUT" | tail -3 | tr '\n' ' ' | cut -c1-300)"
    fi
else
    res FAIL "platform CLI установлен" "бинарник platform не найден даже после fallback-установки"
fi

# ─────────────────────────────────────────────────────────────────────────────
# ШАГ 6. Сборка и запуск core (master + caddy)
# ─────────────────────────────────────────────────────────────────────────────
section "ШАГ 6/10. Сборка и запуск core-сервисов (master + caddy)"
STEP="Шаг 6: запуск core"

if $LIVE_STACK; then
    # Без даунтайма: docker compose up --build сначала собирает новый образ,
    # пока старый контейнер продолжает работать, и лишь затем пересоздаёт его
    # (секунды недоступности вместо минут на время сборки). Никаких `down`.
    COMPOSE_ENV_ARGS=()
    [ -f "$ENV_FILE" ] && COMPOSE_ENV_ARGS+=(--env-file "$ENV_FILE")
    log "Обновление core БЕЗ остановки: сборка master при работающем старом контейнере"
    if ! run docker compose "${COMPOSE_ENV_ARGS[@]}" -f "$APPS_ROOT/_core/master/docker-compose.yml" up -d --build; then
        dump_diagnostics
        die "Пересборка master не удалась — см. диагностику выше"
    fi
    run docker compose "${COMPOSE_ENV_ARGS[@]}" -f "$APPS_ROOT/_core/caddy/docker-compose.yml" up -d
    if docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
        ok "Caddy: конфиг перезагружен без даунтайма"
    else
        warn "Caddy reload не удался — конфиг подхватится при старте/через watcher"
    fi
else
    log "Запуск restart_core.sh --build (сборка образа master может занять несколько минут)"
    if ! (cd "$APPS_ROOT" && run ./restart_core.sh --build); then
        die "restart_core.sh завершился с ошибкой. Проверьте вывод выше (сборка образа / docker compose)."
    fi
fi

log "Ожидание готовности master ($MASTER_URL/healthz), до 180 секунд..."
MASTER_UP=false
MASTER_FAIL_REASON=""
for _ in $(seq 1 60); do
    MSTATE=$(docker inspect -f '{{.State.Status}}|{{.RestartCount}}|{{.State.ExitCode}}' "$MASTER_CONTAINER" 2>/dev/null || echo "missing|0|0")
    MSTATUS="${MSTATE%%|*}"
    if [ "$MSTATUS" = "missing" ]; then
        MASTER_FAIL_REASON="контейнер $MASTER_CONTAINER не найден"
        break
    fi
    if [ "$MSTATUS" != "running" ]; then
        MASTER_FAIL_REASON="контейнер $MASTER_CONTAINER в состоянии '$MSTATUS' (exit=${MSTATE##*|}) — вероятно, падает при старте"
        break
    fi
    CODE=$(http_code "$MASTER_URL/healthz")
    if [ "$CODE" = "200" ]; then
        MASTER_UP=true
        break
    fi
    sleep 3
done

if $MASTER_UP; then
    res PASS "Master отвечает на /healthz" "$MASTER_URL/healthz"
else
    [ -n "$MASTER_FAIL_REASON" ] || MASTER_FAIL_REASON="тайм-аут 180s, последний HTTP-код: $CODE"
    res FAIL "Master отвечает на /healthz" "$MASTER_FAIL_REASON"
    dump_diagnostics
    die "Master не поднялся — без него дальнейшие проверки бессмысленны. Диагностика выше (docker logs $MASTER_CONTAINER)."
fi

if OUT=$(wait_http "$MASTER_URL/readyz" 60); then
    READY_BODY=$(curl -s --noproxy '*' -m 10 "$MASTER_URL/readyz" || true)
    res PASS "Master готов (/readyz 200)" "$(echo "$READY_BODY" | tr '\n' ' ' | cut -c1-200)"
else
    res FAIL "Master готов (/readyz 200)" "$OUT"
fi

if docker inspect -f '{{.State.Running}}' "$CADDY_CONTAINER" 2>/dev/null | grep -q true; then
    res PASS "Контейнер $CADDY_CONTAINER запущен" "$(docker inspect -f '{{.State.Status}}' "$CADDY_CONTAINER")"
else
    res FAIL "Контейнер $CADDY_CONTAINER запущен" "не найден или остановлен"
    hint "docker logs $CADDY_CONTAINER --tail 50"
fi

CODE=$(http_code "http://127.0.0.1/")
if [ "$CODE" = "200" ] || [ "$CODE" = "404" ]; then
    res PASS "Caddy отвечает на порту 80" "HTTP $CODE"
else
    res FAIL "Caddy отвечает на порту 80" "HTTP $CODE"
fi

# ─────────────────────────────────────────────────────────────────────────────
# ШАГ 7. Admin-пользователь для API (builtin auth)
# ─────────────────────────────────────────────────────────────────────────────
section "ШАГ 7/10. Admin-пользователь API (builtin auth)"
STEP="Шаг 7: admin-пользователь"

# В builtin-режиме нет login-endpoint: API-токеном служит числовой id пользователя.
# Создаём суперпользователя штатной моделью приложения внутри контейнера.
ADMIN_PASSWORD=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)
log "Создание/проверка пользователя 'admin' в $MASTER_CONTAINER (пароль генерируется)"
SEED_OUT=$(docker exec -i -w /app -e SMOKE_ADMIN_PASSWORD="$ADMIN_PASSWORD" "$MASTER_CONTAINER" python3 - <<'PY' 2>&1
import os, sys
from app.core.database import db_manager, SessionLocal
from app.models.user import User

db_manager.create_tables()
db = SessionLocal()
try:
    user = db.query(User).filter(User.username == "admin").first()
    if user is None:
        user = User(username="admin", email="admin@localhost", is_active=True, is_superuser=True)
        user.password = os.environ["SMOKE_ADMIN_PASSWORD"]
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"CREATED id={user.id}")
    else:
        user.is_superuser = True
        user.is_active = True
        db.commit()
        print(f"EXISTS id={user.id}")
finally:
    db.close()
PY
) || true
echo "$SEED_OUT" | sed 's/^/    | /'

if [[ "$SEED_OUT" =~ (CREATED|EXISTS)\ id=([0-9]+) ]]; then
    ADMIN_UID="${BASH_REMATCH[2]}"
    CREDS_FILE="$APPS_ROOT/.platform-credentials"
    {
        echo "# Platform API credentials (generated $(date -u +%FT%TZ) by install-server.sh)"
        echo "# В builtin-режиме токен API = числовой id пользователя."
        echo "MASTER_URL=$MASTER_URL"
        echo "API_TOKEN=$ADMIN_UID"
        echo "ADMIN_USERNAME=admin"
        echo "ADMIN_PASSWORD=$ADMIN_PASSWORD"
        echo ""
        echo "# Пример запроса:"
        echo "# curl -H 'Authorization: Bearer $ADMIN_UID' $MASTER_URL/api/services/"
    } > "$CREDS_FILE"
    chmod 0600 "$CREDS_FILE"
    res PASS "Admin-пользователь API создан" "id=$ADMIN_UID, учётные данные: $CREDS_FILE"
else
    res FAIL "Admin-пользователь API создан" "$SEED_OUT" \
        || true
fi

# smoke-проверка авторизованного API
if [ -n "$ADMIN_UID" ]; then
    CODE=$(curl -s --noproxy '*' -o "$TMP_DIR/api_services.json" -w '%{http_code}' -m 10 \
        -H "Authorization: Bearer $ADMIN_UID" "$MASTER_URL/api/services/")
    if [ "$CODE" = "200" ]; then
        res PASS "API /api/services/ доступен с Bearer-токеном" "HTTP 200"
    else
        res FAIL "API /api/services/ доступен с Bearer-токеном" "HTTP $CODE: $(head -c 200 "$TMP_DIR/api_services.json" 2>/dev/null)"
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# ШАГ 8. Деплой тестового сервиса smoke-test
# ─────────────────────────────────────────────────────────────────────────────
section "ШАГ 8/10. Развёртывание тестового сервиса ($TEST_SERVICE)"
STEP="Шаг 8: деплой $TEST_SERVICE"

TEST_DIR="$APPS_ROOT/services/public/$TEST_SERVICE"

if $SKIP_TEST_SERVICE; then
    warn "--skip-test-service: деплой тестового сервиса пропущен"
else
    if [ -d "$TEST_DIR" ]; then
        warn "$TEST_DIR уже существует — файлы сервиса (service.yml/docker-compose/nginx.conf) будут перезаписаны"
    fi

    log "Создание файлов сервиса в $TEST_DIR"
    mkdir -p "$TEST_DIR"

    cat > "$TEST_DIR/service.yml" <<SVC_EOF
name: ${TEST_SERVICE}
display_name: "Smoke Test (install-server.sh)"
version: "1.0.0"
description: "Сервис-самопроверка установки платформы: routing, discovery, health, caddy"
type: docker-compose
visibility: public

routing:
  - type: subfolder
    base_domain: localhost
    path: ${TEST_PATH}
    strip_prefix: true
    internal_port: 80
    container_name: ${TEST_SERVICE}

health:
  enabled: true
  endpoint: /
  interval: 30s
  timeout: 5s
  retries: 3

backup:
  enabled: false
SVC_EOF

    cat > "$TEST_DIR/docker-compose.yml" <<CMP_EOF
services:
  ${TEST_SERVICE}:
    image: nginx:alpine
    container_name: ${TEST_SERVICE}
    restart: unless-stopped
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    networks:
      - platform

networks:
  platform:
    external: true
    name: ${PLATFORM_NETWORK}
CMP_EOF

    cat > "$TEST_DIR/nginx.conf" <<NGX_EOF
server {
    listen 80;
    server_name _;
    default_type text/plain;
    location / {
        return 200 '${TEST_MARKER}';
    }
}
NGX_EOF

    run chmod 0644 "$TEST_DIR/service.yml" "$TEST_DIR/docker-compose.yml" "$TEST_DIR/nginx.conf"

    log "Деплой через platform CLI: platform deploy $TEST_SERVICE"
    if ! run platform deploy "$TEST_SERVICE"; then
        warn "platform deploy не удался — пробуем напрямую docker compose up"
        run docker compose --project-directory "$TEST_DIR" -f "$TEST_DIR/docker-compose.yml" up -d
    fi

    # Ожидание контейнера
    for _ in $(seq 1 20); do
        if docker inspect -f '{{.State.Running}}' "$TEST_SERVICE" 2>/dev/null | grep -q true; then
            break
        fi
        sleep 2
    done
    if docker inspect -f '{{.State.Running}}' "$TEST_SERVICE" 2>/dev/null | grep -q true; then
        res PASS "Контейнер $TEST_SERVICE запущен" "$(docker inspect -f '{{.State.Status}}' "$TEST_SERVICE")"
    else
        res FAIL "Контейнер $TEST_SERVICE запущен" "не запустился за 40 секунд"
        hint "docker logs $TEST_SERVICE --tail 50"
    fi

    # Discovery + генерация Caddy-конфига: master должен увидеть service.yml
    # (watcher) и сгенерировать conf.d/*.caddy. Если сеть событий не сработала —
    # дёргаем файлом service.yml для повторного триггера.
    log "Ожидание генерации Caddy-конфига для $TEST_SERVICE (watcher/discovery)"
    CADDY_CONF_FOUND=false
    for attempt in 1 2 3 4 5 6 7 8 9 10; do
        if grep -rqs "$TEST_SERVICE" "$APPS_ROOT/_core/caddy/conf.d/" 2>/dev/null; then
            CADDY_CONF_FOUND=true
            break
        fi
        if [ "$attempt" = "5" ]; then
            warn "Конфиг ещё не сгенерирован — трога service.yml для повторного события watcher"
            touch "$TEST_DIR/service.yml" "$TEST_DIR/docker-compose.yml"
        fi
        sleep 3
    done
    if $CADDY_CONF_FOUND; then
        GEN_FILE=$(grep -rls "$TEST_SERVICE" "$APPS_ROOT/_core/caddy/conf.d/" | head -1)
        res PASS "Caddy-конфиг сгенерирован (discovery + regenerate)" "$(basename "$GEN_FILE")"
    else
        res FAIL "Caddy-конфиг сгенерирован (discovery + regenerate)" "в conf.d нет упоминаний $TEST_SERVICE"
        hint "docker logs $MASTER_CONTAINER 2>&1 | grep -i -E 'discovery|caddy|error'"
    fi

    # Маршрутизация через Caddy. В prod для сайта localhost Caddy открывает
    # ТОЛЬКО :443 (внутренний CA, auto_https), :80 может не слушаться вовсе —
    # поэтому пробуем HTTP и HTTPS (проверено: https://localhost<путь>/ -> 200).
    log "Проверка маршрута через Caddy (HTTP и HTTPS, Host: localhost)"
    ROUTED=false
    ROUTE_VIA=""
    LAST_CODE=""
    for _ in $(seq 1 20); do
        LAST_CODE=$(curl -s --noproxy '*' -o "$TMP_DIR/smoke_body.txt" -w '%{http_code}' -m 10 \
            -H "Host: localhost" "http://127.0.0.1${TEST_PATH}/" 2>/dev/null) || LAST_CODE="000"
        if [ "$LAST_CODE" = "200" ] && grep -q "$TEST_MARKER" "$TMP_DIR/smoke_body.txt" 2>/dev/null; then
            ROUTED=true; ROUTE_VIA="HTTP :80"; break
        fi
        LAST_CODE=$(curl -sk --noproxy '*' -o "$TMP_DIR/smoke_body.txt" -w '%{http_code}' -m 10 \
            "https://localhost${TEST_PATH}/" 2>/dev/null) || LAST_CODE="000"
        if [ "$LAST_CODE" = "200" ] && grep -q "$TEST_MARKER" "$TMP_DIR/smoke_body.txt" 2>/dev/null; then
            ROUTED=true; ROUTE_VIA="HTTPS :443 (внутренний CA)"; break
        fi
        sleep 3
    done
    if $ROUTED; then
        res PASS "Маршрут через Caddy работает (${TEST_PATH}/)" "HTTP 200 через $ROUTE_VIA, тело содержит $TEST_MARKER"
    else
        res FAIL "Маршрут через Caddy работает (${TEST_PATH}/)" "HTTP $LAST_CODE, тело: $(head -c 120 "$TMP_DIR/smoke_body.txt" 2>/dev/null)"
        hint "docker exec caddy caddy validate --config /etc/caddy/Caddyfile"
        hint "tail -50 $APPS_ROOT/_core/caddy/logs/debug.log"
    fi

    # То же с заголовком Host: $PLATFORM_DOMAIN (если домен отличается от localhost)
    if [ "$PLATFORM_DOMAIN" != "localhost" ]; then
        ALT_CODE=$(curl -s --noproxy '*' -o /dev/null -w '%{http_code}' -m 10 \
            -H "Host: $PLATFORM_DOMAIN" "http://127.0.0.1${TEST_PATH}/" 2>/dev/null) || ALT_CODE="000"
        res WARN "Маршрут с Host: $PLATFORM_DOMAIN" "HTTP $ALT_CODE (subfolder smoke-test привязан к localhost; для прод-домена создайте сервис с base_domain: $PLATFORM_DOMAIN)"
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# ШАГ 9. Проверка основных функций платформы
# ─────────────────────────────────────────────────────────────────────────────
section "ШАГ 9/10. Проверка основных функций платформы"
STEP="Шаг 9: проверки"

# 9.1 Core-контейнеры
for c in "$MASTER_CONTAINER" "$CADDY_CONTAINER"; do
    if docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null | grep -q true; then
        res PASS "Контейнер $c работает" "$(docker inspect -f '{{.State.Status}} / {{.HostConfig.RestartPolicy.Name}}' "$c")"
    else
        res FAIL "Контейнер $c работает" "не запущен"
    fi
done

# 9.2 Сеть
if docker network inspect "$PLATFORM_NETWORK" >/dev/null 2>&1; then
    NET_MEMBERS=$(docker network inspect -f '{{range .Containers}}{{.Name}} {{end}}' "$PLATFORM_NETWORK" 2>/dev/null)
    res PASS "Сеть $PLATFORM_NETWORK" "контейнеры: ${NET_MEMBERS:-<пока пусто>}"
else
    res FAIL "Сеть $PLATFORM_NETWORK" "не найдена"
fi

# 9.3 Master: healthz / readyz / metrics / UI
CODE=$(http_code "$MASTER_URL/healthz"); [ "$CODE" = "200" ] \
    && res PASS "Master /healthz" "HTTP 200" \
    || res FAIL "Master /healthz" "HTTP $CODE"
CODE=$(http_code "$MASTER_URL/readyz"); [ "$CODE" = "200" ] \
    && res PASS "Master /readyz (db/discovery/caddy)" "HTTP 200" \
    || res FAIL "Master /readyz (db/discovery/caddy)" "HTTP $CODE"
CODE=$(http_code "$MASTER_URL/metrics"); [ "$CODE" = "200" ] \
    && res PASS "Master /metrics (Prometheus)" "HTTP 200" \
    || res WARN "Master /metrics (Prometheus)" "HTTP $CODE"
CODE=$(http_code "$MASTER_URL/"); [ "$CODE" = "200" ] \
    && res PASS "Веб-интерфейс UI на :8001" "HTTP 200" \
    || res FAIL "Веб-интерфейс UI на :8001" "HTTP $CODE"

# 9.4 Caddy admin API + валидность конфига
if curl -fsS --noproxy '*' -m 10 "$CADDY_ADMIN_URL/config/" > "$TMP_DIR/caddy_config.json" 2>/dev/null; then
    res PASS "Caddy admin API ($CADDY_ADMIN_URL)" "конфиг отдан"
else
    res FAIL "Caddy admin API ($CADDY_ADMIN_URL)" "не отвечает (порт 2019 слушается только на 127.0.0.1)"
fi
if docker exec "$CADDY_CONTAINER" caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
    res PASS "Caddyfile валиден (caddy validate)" "OK"
else
    res WARN "Caddyfile валиден (caddy validate)" "$(docker exec "$CADDY_CONTAINER" caddy validate --config /etc/caddy/Caddyfile 2>&1 | tail -2 | tr '\n' ' ')"
fi

# 9.5 Discovery: сервис виден через API
if [ -n "$ADMIN_UID" ] && ! $SKIP_TEST_SERVICE; then
    curl -s --noproxy '*' -m 10 -H "Authorization: Bearer $ADMIN_UID" "$MASTER_URL/api/services/" > "$TMP_DIR/api_services2.json" || true
    if grep -q "$TEST_SERVICE" "$TMP_DIR/api_services2.json" 2>/dev/null; then
        res PASS "Discovery: $TEST_SERVICE виден в /api/services/" "OK"
    else
        res FAIL "Discovery: $TEST_SERVICE виден в /api/services/" "не найден в ответе API"
    fi

    # 9.6 Health-функция: API отвечает и выполняет проверку
    curl -s --noproxy '*' -m 15 -H "Authorization: Bearer $ADMIN_UID" \
        "$MASTER_URL/api/health/service/$TEST_SERVICE" > "$TMP_DIR/api_health.json" || true
    if grep -q 'is_healthy' "$TMP_DIR/api_health.json" 2>/dev/null; then
        HEALTH_VAL=$(grep -o '"is_healthy":[^,]*' "$TMP_DIR/api_health.json" | head -1)
        ERR_VAL=$(grep -o '"error":[^,}]*' "$TMP_DIR/api_health.json" | head -1)
        if grep -q '"is_healthy":true' "$TMP_DIR/api_health.json"; then
            res PASS "Health-мониторинг сервиса (API /api/health)" "$HEALTH_VAL"
        else
            res WARN "Health-мониторинг сервиса (API /api/health)" "функция отвечает, но $HEALTH_VAL $ERR_VAL — health-checker платформы ходит на https://<base_domain>/<path>/, для localhost-smoke-теста это ожидаемо"
        fi
    else
        res WARN "Health-мониторинг сервиса (API /api/health)" "ответ: $(head -c 150 "$TMP_DIR/api_health.json" 2>/dev/null)"
    fi
fi

# 9.7 CLI
if ! $SKIP_TEST_SERVICE; then
    if OUT=$(platform list 2>&1) && echo "$OUT" | grep -q "$TEST_SERVICE"; then
        res PASS "CLI: platform list видит $TEST_SERVICE" "OK"
    else
        res FAIL "CLI: platform list видит $TEST_SERVICE" "$(echo "$OUT" | tail -3 | tr '\n' ' ' | cut -c1-200)"
    fi
    if OUT=$(platform logs "$TEST_SERVICE" -n 5 2>&1); then
        res PASS "CLI: platform logs $TEST_SERVICE" "OK"
    else
        res WARN "CLI: platform logs $TEST_SERVICE" "$(echo "$OUT" | tail -2 | tr '\n' ' ' | cut -c1-200)"
    fi
fi
if OUT=$(ops list 2>&1); then
    res PASS "CLI: ops list работает" "OK"
else
    res WARN "CLI: ops list работает" "$(echo "$OUT" | tail -2 | tr '\n' ' ' | cut -c1-200)"
fi
if platform --help 2>/dev/null | grep -q backup; then
    res PASS "CLI: команды backup доступны" "platform backup"
else
    res WARN "CLI: команды backup доступны" "команда backup не найдена в platform --help"
fi

# 9.8 Логи пишутся (важно для отладки)
if [ -s "$APPS_ROOT/_core/caddy/logs/access.log" ] || docker logs --tail 1 "$MASTER_CONTAINER" >/dev/null 2>&1; then
    res PASS "Логи доступны (master stdout / caddy access.log)" "caddy: _core/caddy/logs/"
else
    res WARN "Логи доступны (master stdout / caddy access.log)" "пока пусты"
fi

# 9.9 Файрвол — информационно
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q 'Status: active'; then
    UFW_PORTS=$(ufw status 2>/dev/null | awk '/^[0-9]/ {print $1}' | tr '\n' ' ')
    MISSING=""
    for p in 80/tcp 443/tcp; do
        echo " $UFW_PORTS " | grep -q " $p " || MISSING="$MISSING $p"
    done
    echo " $UFW_PORTS " | grep -q " 8001/tcp " || MISSING="$MISSING 8001/tcp(UI)"
    if [ -n "$MISSING" ]; then
        res WARN "Файрвол ufw активен" "не открыты:$MISSING (уже открытые: $UFW_PORTS)"
    else
        res PASS "Файрвол ufw активен" "нужные порты открыты: $UFW_PORTS"
    fi
else
    res PASS "Файрвол ufw" "не активен — порты 80/443/8001 доступны (настраивайте security groups/iptables при необходимости)"
fi

# ─────────────────────────────────────────────────────────────────────────────
# ШАГ 10. Диагностика окружения + итоговый отчёт
# ─────────────────────────────────────────────────────────────────────────────
section "ШАГ 10/10. Диагностика окружения и итоговый отчёт"
STEP="Шаг 10: отчёт"

# Полный срез состояния в лог — чтобы любой сбой можно было разобрать постфактум.
dump_diagnostics

SERVER_IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}' | head -1)
ELAPSED=$(( $(date +%s) - BOOTSTRAP_STARTED_AT ))

echo ""
echo "  ┌─────────────────────────────────────────────┐"
echo "  │  Результат:  PASS=$PASS_N   FAIL=$FAIL_N   WARN=$WARN_N              │"
echo "  └─────────────────────────────────────────────┘"
echo ""
printf '  %-6s %s\n' "СТАТУС" "ПРОВЕРКА"
printf '  %-6s %s\n' "------" "--------------------------------------------------"
for row in "${RESULTS[@]}"; do
    st="${row%%|*}"; rest="${row#*|}"
    name="${rest%%|*}"; detail="${rest#*|}"
    case "$st" in
        PASS) col="$G" ;;
        FAIL) col="$R" ;;
        *)    col="$Y" ;;
    esac
    printf "  ${col}%-6s${N} %s${D}%s${N}\n" "$st" "$name" "${detail:+ — $detail}"
done

echo ""
echo "  Время установки: $((ELAPSED / 60)) мин $((ELAPSED % 60)) сек"
echo "  Полный лог:      $LOG_FILE"
echo "  Режим:           $([ "$LIVE_STACK" = true ] && echo 'обновление работающей платформы' || echo 'чистая установка')"
[ -n "$BACKUP_DIR" ] && echo "  Бэкап состояния: $BACKUP_DIR (откат: восстановить оттуда master.db/services/caddy)"
echo "  Корень проекта:  $APPS_ROOT"
echo "  UI платформы:    http://${SERVER_IP:-<ip-сервера>}:8001  (пока без авторизации)"
if [ -f "$APPS_ROOT/.platform-credentials" ]; then
    echo "  API-токен:       $APPS_ROOT/.platform-credentials (API_TOKEN / ADMIN_PASSWORD)"
    if [ -n "$ADMIN_UID" ]; then
        echo "  Пример API:      curl -H 'Authorization: Bearer $ADMIN_UID' $MASTER_URL/api/services/"
    fi
fi
if ! $SKIP_TEST_SERVICE; then
    echo "  Тест-сервис:     маршрут с Host: localhost (subfolder ${TEST_PATH}/)"
    echo "                   с сервера:  curl -H 'Host: localhost' http://127.0.0.1${TEST_PATH}/"
    echo "                   снаружи:    curl -H 'Host: localhost' http://${SERVER_IP:-<ip-сервера>}${TEST_PATH}/"
fi
echo ""
echo "  Основные команды для эксплуатации и отладки:"
echo "    platform list | platform status <svc> | platform logs <svc> -f"
echo "    platform deploy <svc> --build | platform stop <svc> | platform backup <svc>"
echo "    ops list | ops up <svc> | ops logs <svc> | ops reload"
echo "    docker logs -f $MASTER_CONTAINER --tail 100"
echo "    tail -f $APPS_ROOT/_core/caddy/logs/access.log"
echo "    tail -f $APPS_ROOT/_core/caddy/logs/debug.log"
echo "    SERVICE_NAME=<svc> bash $APPS_ROOT/docs/diagnostics/diagnose-server.sh"
echo "    $APPS_ROOT/update-platform.sh    # обновление платформы"
echo ""

if [ "$FAIL_N" -gt 0 ]; then
    warn "Есть НЕ пройденные проверки (FAIL=$FAIL_N) — смотрите вывод выше и лог."
    finish 1
fi

ok "Установка завершена успешно. Основные функции платформы проверены."
if [ "$WARN_N" -gt 0 ]; then
    warn "Осталось предупреждений: $WARN_N (не блокируют работу)."
fi
finish 0
