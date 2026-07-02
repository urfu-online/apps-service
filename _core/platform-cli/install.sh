#!/bin/bash
# Скрипт установки Platform CLI.
#
# Поддерживает два режима:
#   --system   (production) системная установка через pipx в /opt/pipx с
#              симлинком в /usr/local/bin/platform — доступна всем пользователям.
#              Требует sudo / root.
#   по умолчанию (dev) per-user установка в ~/.local через pipx.
#
# После установки CLI резолвит корень проекта автоматически (см. get_project_root()
# в apps_platform/cli.py), поэтому запуск возможен из любой директории и любым
# пользователем без правки настроек.

set -euo pipefail

# --- helpers ---
log() { echo -e "\033[0;34mℹ️  $1\033[0m"; }
ok()   { echo -e "\033[0;32m✅ $1\033[0m"; }
warn() { echo -e "\033[1;33m⚠️  $1\033[0m"; }
err()  { echo -e "\033[0;31m❌ $1\033[0m" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_DIR="$SCRIPT_DIR"

# Системные пути для системной установки.
SYSTEM_PIPX_HOME="/opt/pipx"
SYSTEM_PIPX_BIN_DIR="/usr/local/bin"
SYSTEM_VENV_DIR="${SYSTEM_PIPX_HOME}/venvs/platform-cli"

# --- режим установки ---
SYSTEM_INSTALL=false
if [[ "${1:-}" == "--system" ]]; then
    SYSTEM_INSTALL=true
fi

echo "🚀 Установка Platform CLI"
echo "========================="
echo ""
echo "📍 Platform CLI directory: $CLI_DIR"
if $SYSTEM_INSTALL; then
    echo "📍 Режим: системный (production) -> ${SYSTEM_PIPX_BIN_DIR}/platform"
else
    echo "📍 Режим: пользовательский (dev) -> ~/.local/bin/platform"
fi
echo ""

# --- проверка Python ---
if ! command -v python3 &> /dev/null; then
    err "Python3 не найден. Установите Python 3.11+"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
ok "$PYTHON_VERSION"

# --- проверка pip ---
if ! python3 -m pip --version &> /dev/null; then
    warn "pip не найден. Установка..."
    if command -v apt &> /dev/null; then
        sudo apt update && sudo apt install -y python3-pip python3-venv
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y python3-pip
    elif command -v yum &> /dev/null; then
        sudo yum install -y python3-pip
    else
        err "Не удалось установить pip. Установите его вручную."
        exit 1
    fi
fi
ok "$(python3 -m pip --version)"

# --- установка pipx (при необходимости) ---
ensure_pipx() {
    # $1 = целевой PIPX_HOME, $2 = целевой BIN_DIR
    local home_dir="$1" bin_dir="$2"
    if [[ ! -x "${home_dir}/bin/pipx" ]]; then
        log "Установка pipx в ${home_dir}..."
        python3 -m pip install --target "${home_dir}/pipx-installer" pipx
        mkdir -p "${home_dir}/bin"
        # Wrapper: запускает pipx как модуль с фиксированными PIPX_HOME/BIN_DIR.
        cat > "${home_dir}/bin/pipx" <<PIPX_WRAPPER
#!/bin/bash
export PIPX_HOME="${home_dir}"
export PIPX_BIN_DIR="${bin_dir}"
export PYTHONPATH="${home_dir}/pipx-installer:\$PYTHONPATH"
exec python3 -m pipx "\$@"
PIPX_WRAPPER
        chmod +x "${home_dir}/bin/pipx"
    fi
}

if $SYSTEM_INSTALL; then
    # --- системная установка: pipx в /opt/pipx, симлинк в /usr/local/bin ---
    if [[ $EUID -ne 0 ]]; then
        log "Требуются права root для системной установки. Перезапуск через sudo..."
        # Запускаемся в чистом окружении, чтобы BASH_ENV/PYTHONPATH/LD_PRELOAD/PATH
        # вызывающего не перетекли в root-процесс (защита от privilege escalation).
        exec sudo -- env -i \
            HOME="${HOME:-/root}" \
            PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
            bash "$0" --system
    fi

    log "Подготовка системного окружения pipx (${SYSTEM_PIPX_HOME})..."
    install -d -m 0755 "${SYSTEM_PIPX_HOME}"
    install -d -m 0755 "${SYSTEM_PIPX_HOME}/venvs"

    # pipx должен быть доступен системно. Предпочитаем системный pipx.
    if command -v pipx &> /dev/null; then
        PIPX_BIN="pipx"
    else
        ensure_pipx "${SYSTEM_PIPX_HOME}" "${SYSTEM_PIPX_BIN_DIR}"
        PIPX_BIN="${SYSTEM_PIPX_HOME}/bin/pipx"
    fi

    log "Установка platform-cli в системное окружение..."
    export PIPX_HOME="${SYSTEM_PIPX_HOME}"
    export PIPX_BIN_DIR="${SYSTEM_PIPX_BIN_DIR}"

    "${PIPX_BIN}" install --force "$CLI_DIR"

    # Симлинк в /usr/local/bin (pipx создаёт его сам, но гарантируем
    # наличие для всех пользователей через системный PATH).
    ln -sf "${SYSTEM_VENV_DIR}/bin/platform" "${SYSTEM_PIPX_BIN_DIR}/platform"
    chmod 0755 "${SYSTEM_PIPX_BIN_DIR}/platform" 2>/dev/null || true

    ok "Системная установка завершена"
    echo ""
    echo "Использование (доступно всем пользователям):"
    echo "  platform --help"
    echo "  platform list"
    echo ""
    warn "Для доступа к Docker пользователям нужно состоять в группе 'platform-admins':"
    echo "  sudo usermod -aG platform-admins <username>  # затем перелогин"
else
    # --- пользовательская установка: pipx в ~/.local (dev) ---
    if ! command -v pipx &> /dev/null; then
        warn "pipx не найден. Установка..."
        python3 -m pip install --user pipx
        python3 -m pipx ensurepath 2>/dev/null || true
        export PATH="$HOME/.local/bin:$PATH"
        if ! command -v pipx &> /dev/null; then
            err "Не удалось установить pipx. Попробуйте вручную:"
            echo "   python3 -m pip install --user pipx"
            echo "   python3 -m pipx ensurepath"
            exit 1
        fi
    fi
    ok "pipx $(pipx --version)"

    log "Установка platform-cli (пользовательская)..."
    if pipx list | grep -q "platform-cli"; then
        log "platform-cli уже установлен. Обновление..."
        pipx upgrade platform-cli
    else
        pipx install "$CLI_DIR"
    fi

    ok "Пользовательская установка завершена"
fi

echo ""
echo "ℹ️  Корень проекта резолвится автоматически (маркер .ops-root /"
echo "    системный конфиг / OPS_PROJECT_ROOT). Подробнее: apps_platform/cli.py -> get_project_root()"
