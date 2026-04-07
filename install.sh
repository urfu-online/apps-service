#!/bin/bash
set -uo pipefail

log() { echo -e "\033[0;34mℹ️  $1\033[0m"; }
ok() { echo -e "\033[0;32m✅ $1\033[0m"; }
warn() { echo -e "\033[1;33m⚠️  $1\033[0m"; }
err() { echo -e "\033[0;31m❌ $1\033[0m" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Ops Manager Installation"
echo "=========================="
echo ""
echo "Установка включает:"
echo "  • ops — базовая CLI утилита (обязательно)"
echo "  • platform — расширенная CLI утилита (опционально)"
echo ""
echo "📍 Found project at: $SCRIPT_DIR"
echo ""

echo "Select environment type:"
echo "  [l] Local development (your laptop)"
echo "  [s] Server production (VPS/cloud - /apps)"
echo "  [c] Custom"
read -rp "Choice [l/s/c]: " ENV_TYPE

case "$ENV_TYPE" in
    l|L)
        DEFAULT_ROOT="$SCRIPT_DIR"  # Теперь корень = проект
        ENV_NAME="local"
        ;;
    s|S)
        DEFAULT_ROOT="/apps"        # На сервере /apps содержит _core/, services/
        ENV_NAME="server"
        ;;
    c|C)
        DEFAULT_ROOT="$SCRIPT_DIR"
        ENV_NAME="custom"
        ;;
    *)
        echo "Invalid choice, exiting"
        exit 1
        ;;
esac

echo ""
read -rp "Path to project root (where _core/, services/ are) [$DEFAULT_ROOT]: " PROJECT_ROOT
PROJECT_ROOT="${PROJECT_ROOT:-$DEFAULT_ROOT}"

# Define config file after PROJECT_ROOT is set
CONFIG_FILE="$PROJECT_ROOT/.ops-config.yml"

# Validate
if [[ ! -d "$PROJECT_ROOT" ]]; then
    warn "Directory $PROJECT_ROOT not found. Create? [y/N]"
    read -r CREATE
    if [[ "$CREATE" =~ ^[yY] ]]; then
        mkdir -p "$PROJECT_ROOT"
    else
        exit 1
    fi
fi

# Check structure
if [[ ! -d "$PROJECT_ROOT/_core" && ! -d "$PROJECT_ROOT/services" ]]; then
    warn "No _core/ or services/ found in $PROJECT_ROOT"
    warn "Expected structure: $PROJECT_ROOT/_core/master/docker-compose.yml"
    echo "Continue anyway? [y/N]"
    read -r CONTINUE
    [[ "$CONTINUE" =~ ^[yY] ]] || exit 1
fi

# Normalize to absolute path
PROJECT_ROOT="$(cd "$PROJECT_ROOT" && pwd)"

# --- Ask for install location ---
echo ""
echo "Where to install 'ops' command?"
echo "  [1] ~/bin (recommended, no sudo needed)"
echo "  [2] /usr/local/bin (system-wide, needs sudo)"
echo "  [3] Current dir only ($SCRIPT_DIR)"
read -rp "Choice [1/2/3]: " INSTALL_CHOICE

case "$INSTALL_CHOICE" in
    1) TARGET="$HOME/bin" ;;
    2) TARGET="/usr/local/bin" ;;
    3) TARGET="$SCRIPT_DIR" ;;
    *) TARGET="$HOME/bin" ;;
esac

mkdir -p "$TARGET" 2>/dev/null || true

# --- Ask about Platform CLI installation ---
echo ""
echo "📦 Platform CLI — расширенная CLI утилита с дополнительными возможностями:"
echo "   • platform new — создание сервисов из шаблона"
echo "   • platform deploy — деплой с опциями --build/--pull"
echo "   • platform status/logs/backup — расширенное управление"
echo "   • Устанавливается через pipx (изолированно)"
echo ""
read -rp "Install Platform CLI? [Y/n]: " INSTALL_PLATFORM
INSTALL_PLATFORM="${INSTALL_PLATFORM:-Y}"

INSTALL_PLATFORM_CLI=false
if [[ "$INSTALL_PLATFORM" =~ ^[yY] ]]; then
    INSTALL_PLATFORM_CLI=true
fi

# --- Create config ---
log "Creating config at $CONFIG_FILE..."

cat > "$CONFIG_FILE" << EOF
# Ops Manager Configuration
# Generated: $(date)
environment: $ENV_NAME
project_root: $PROJECT_ROOT

# Service paths (relative to project_root)
core_path: _core
services_path: services

# Docker settings
docker_host: unix:///var/run/docker.sock
EOF

ok "Config saved to $CONFIG_FILE"

# --- Install ops script ---
log "Installing ops to $TARGET..."

OPS_SCRIPT="$TARGET/ops"

cat > "$OPS_SCRIPT" << 'OPS_EOF'
#!/bin/bash
set -euo pipefail

# Config locations
CONFIG_CANDIDATES=(
    "$PWD/.ops-config.yml"
    "$(dirname "$0")/.ops-config.yml"
    "$HOME/.config/ops-manager/config.yml"
)

CONFIG_FILE=""
for cfg in "${CONFIG_CANDIDATES[@]}"; do
    [[ -f "$cfg" ]] && { CONFIG_FILE="$cfg"; break; }
done

if [[ -z "$CONFIG_FILE" ]]; then
    err "Config not found. Run ./install.sh first" >&2
    exit 1
fi

# Parse YAML (simple)
get_val() { grep "^$1:" "$CONFIG_FILE" | cut -d':' -f2- | sed 's/^[[:space:]]*//'; }

PROJECT_ROOT="$(get_val "project_root")"
ENV_TYPE="$(get_val "environment")"
CORE_PATH="${CORE_PATH:-_core}"
SERVICES_PATH="${SERVICES_PATH:-services}"

[[ -d "$PROJECT_ROOT" ]] || { err "Project root not found: $PROJECT_ROOT"; exit 1; }

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log() { echo -e "${BLUE}ℹ️  $1${NC}"; }
ok() { echo -e "${GREEN}✅ $1${NC}"; }
err() { echo -e "${RED}❌ $1${NC}" >&2; }

# Service discovery (no cd!)
declare -A SERVICES=()

scan_services() {
    SERVICES=()
    
    # Core services: $PROJECT_ROOT/_core/*
    local core_dir="$PROJECT_ROOT/$CORE_PATH"
    if [[ -d "$core_dir" ]]; then
        for svc_dir in "$core_dir"/*/; do
            [[ -f "$svc_dir/docker-compose.yml" ]] && SERVICES[$(basename "$svc_dir")]="$svc_dir"
        done
    fi
    
    # Regular services: $PROJECT_ROOT/services/{public,internal}/*
    local svc_base="$PROJECT_ROOT/$SERVICES_PATH"
    for subdir in public internal; do
        local type_dir="$svc_base/$subdir"
        [[ -d "$type_dir" ]] || continue
        for svc_dir in "$type_dir"/*/; do
            [[ -f "$svc_dir/docker-compose.yml" ]] && SERVICES[$(basename "$svc_dir")]="$svc_dir"
        done
    done
}

compose_cmd() {
    local svc_dir=$1
    shift
    docker compose --project-directory "$svc_dir" -f "$svc_dir/docker-compose.yml" "$@"
}

cmd_list() {
    scan_services
    printf "\n%-15s %-50s %s\n" "SERVICE" "PATH" "STATUS"
    printf "%s\n" "--------------------------------------------------------------------------------"
    
    for name in "${!SERVICES[@]}"; do
        local dir="${SERVICES[$name]}"
        local status="stopped"
        local running=$(compose_cmd "$dir" ps -q 2>/dev/null | wc -l)
        [[ "$running" -gt 0 ]] && status="running ($running)"
        
        local short_path="${dir#$PROJECT_ROOT/}"
        [[ ${#short_path} -gt 48 ]] && short_path="...${short_path: -45}"
        
        printf "%-15s %-50s %s\n" "$name" "$short_path" "$status"
    done
    echo ""
}

cmd_up() {
    local svc=$1
    shift
    scan_services
    
    local dir="${SERVICES[$svc]:-}"
    if [[ -z "$dir" ]]; then
        # Try direct paths
        for d in "$PROJECT_ROOT/$CORE_PATH/$svc" "$PROJECT_ROOT/$SERVICES_PATH/public/$svc" "$PROJECT_ROOT/$SERVICES_PATH/internal/$svc"; do
            [[ -f "$d/docker-compose.yml" ]] && { dir="$d"; break; }
        done
    fi
    
    [[ -z "$dir" ]] && { err "Service '$svc' not found in $PROJECT_ROOT"; exit 1; }
    
    log "Starting $svc..."
    compose_cmd "$dir" up -d "$@"
    ok "$svc started"
}

cmd_down() {
    local svc=$1
    scan_services
    local dir="${SERVICES[$svc]:-}"
    [[ -z "$dir" ]] && { err "Service '$svc' not found"; exit 1; }
    
    log "Stopping $svc..."
    compose_cmd "$dir" down "$@"
    ok "$svc stopped"
}

cmd_logs() {
    local svc=$1
    scan_services
    local dir="${SERVICES[$svc]:-}"
    [[ -z "$dir" ]] && { err "Service '$svc' not found"; exit 1; }
    compose_cmd "$dir" logs -f --tail=100
}

cmd_ui() {
    local target="${1:-all}"
    
    if ! command -v lazydocker &> /dev/null; then
        err "lazydocker not found. Install: go install github.com/jesseduffield/lazydocker@latest"
        exit 1
    fi
    
    if [[ "$target" == "all" ]]; then
        cd "$PROJECT_ROOT" && lazydocker
    else
        scan_services
        local dir="${SERVICES[$target]:-}"
        [[ -z "$dir" ]] && { err "Service '$target' not found"; exit 1; }
        cd "$dir" && lazydocker
    fi
}

usage() {
    cat << EOF
Ops Manager (env: $ENV_TYPE, root: $PROJECT_ROOT)

Usage: ops <command> [args]

Commands:
  list, ls              List all services
  up <svc> [opts]       Start service
  down <svc> [opts]     Stop service
  logs <svc>            Follow logs
  ui [svc|all]          Open lazydocker (default: all)
  reload                Reload Caddy

Config: $CONFIG_FILE
EOF
}

main() {
    local cmd="${1:-help}"
    shift || true
    
    case "$cmd" in
        list|ls)    scan_services; cmd_list ;;
        up)         [[ $# -eq 0 ]] && { usage; exit 1; }; cmd_up "$@" ;;
        down)       [[ $# -eq 0 ]] && { usage; exit 1; }; cmd_down "$@" ;;
        logs)       [[ $# -eq 0 ]] && { usage; exit 1; }; cmd_logs "$1" ;;
        ui)         cmd_ui "$@" ;;
        reload)     docker exec caddy caddy reload --config /etc/caddy/Caddyfile 2>/dev/null || err "Caddy not running" ;;
        help|--help|-h) usage ;;
        *)
            scan_services
            if [[ -n "${SERVICES[$cmd]:-}" ]]; then
                cmd_up "$cmd" "$@"
            else
                err "Unknown command: $cmd"
                usage
                exit 1
            fi
            ;;
    esac
}

main "$@"
OPS_EOF

chmod +x "$OPS_SCRIPT"

# --- Install platform CLI script (опционально) ---
if [[ "$INSTALL_PLATFORM_CLI" == "true" ]]; then
    log "Installing platform CLI to $TARGET..."

    PLATFORM_SCRIPT="$TARGET/platform"
    PLATFORM_CLI_DIR="$PROJECT_ROOT/_core/platform-cli"

    cat > "$PLATFORM_SCRIPT" << 'PLATFORM_EOF'
#!/bin/bash
# Platform CLI wrapper - запускает platform через pipx или напрямую

# PROJECT_ROOT подставляется при установке
PROJECT_ROOT="__PROJECT_ROOT__"

# Проверка наличия platform (pipx installation)
if command -v platform &> /dev/null; then
    exec platform "$@"
fi

# Fallback: запуск через pipx install
PLATFORM_CLI_DIR="$PROJECT_ROOT/_core/platform-cli"

if [[ -d "$PLATFORM_CLI_DIR" ]]; then
    # Проверка pipx
    if command -v pipx &> /dev/null; then
        echo "⚠️  Установка platform-cli через pipx..."
        pipx install "$PLATFORM_CLI_DIR" && platform "$@"
        exit $?
    fi

    # Fallback: прямой запуск через Python
    if command -v python3 &> /dev/null; then
        cd "$PLATFORM_CLI_DIR" && python3 -m platform.cli "$@"
        exit $?
    fi
fi

echo "❌ platform CLI не найден. Установите:"
echo "   pipx install $PROJECT_ROOT/_core/platform-cli"
echo "   или: cd $PROJECT_ROOT/_core/platform-cli && ./install.sh"
exit 1
PLATFORM_EOF

    # Подставляем реальный PROJECT_ROOT
    sed -i "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" "$PLATFORM_SCRIPT"

    chmod +x "$PLATFORM_SCRIPT"
    ok "Platform CLI wrapper установлен в $PLATFORM_SCRIPT"
else
    echo ""
    warn "Platform CLI не установлен"
    echo "   Для установки позже: pipx install $PROJECT_ROOT/_core/platform-cli"
    echo "   или: cd $PROJECT_ROOT/_core/platform-cli && ./install.sh"
fi

# Add to PATH hint
if [[ "$TARGET" == "$HOME/bin" && ":$PATH:" != *":$HOME/bin:"* ]]; then
    echo ""
    warn "Add $HOME/bin to PATH:"
    echo '   echo "export PATH=\"\$HOME/bin:\$PATH\"" >> ~/.bashrc && source ~/.bashrc'
fi

echo ""
ok "Installation complete!"
echo ""
echo "Quick start:"
echo "  ops list              # Show all services (bash wrapper)"
if [[ "$INSTALL_PLATFORM_CLI" == "true" ]]; then
    echo "  platform list         # Full CLI with all features"
    echo "  platform new myapp    # Create new service"
    echo "  platform deploy myapp # Deploy service"
fi
echo "  ops ui                # Lazydocker for all"
echo ""
echo "Config: $CONFIG_FILE"
echo "Root:   $PROJECT_ROOT"