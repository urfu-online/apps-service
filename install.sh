#!/bin/bash
set -euo pipefail

# === ADD THESE LINES ===
log() { echo -e "\033[0;34mℹ️  $1\033[0m"; }
ok() { echo -e "\033[0;32m✅ $1\033[0m"; }
err() { echo -e "\033[0;31m❌ $1\033[0m" >&2; }
# =======================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.config/ops-manager"
CONFIG_FILE="$CONFIG_DIR/config.yml"

echo "🚀 Ops Manager Installation"
echo "=========================="

# --- Detect current location ---
echo ""
echo "📍 Found project at: $SCRIPT_DIR"
echo ""

# --- Ask for environment type ---
echo "Select environment type:"
echo "  [l] Local development (your laptop)"
echo "  [s] Server production (VPS/cloud)"
echo "  [c] Custom"
read -rp "Choice [l/s/c]: " ENV_TYPE

case "$ENV_TYPE" in
    l|L)
        DEFAULT_APPS="$SCRIPT_DIR/apps"
        ENV_NAME="local"
        ;;
    s|S)
        DEFAULT_APPS="/apps"
        ENV_NAME="server"
        ;;
    c|C)
        DEFAULT_APPS="$SCRIPT_DIR/apps"
        ENV_NAME="custom"
        ;;
    *)
        echo "Invalid choice, exiting"
        exit 1
        ;;
esac

# --- Ask for apps path ---
echo ""
read -rp "Path to apps directory [$DEFAULT_APPS]: " APPS_ROOT
APPS_ROOT="${APPS_ROOT:-$DEFAULT_APPS}"

# Validate
if [[ ! -d "$APPS_ROOT" ]]; then
    echo "⚠️  Directory $APPS_ROOT not found. Create? [y/N]"
    read -r CREATE
    if [[ "$CREATE" =~ ^[yY] ]]; then
        mkdir -p "$APPS_ROOT"
    else
        exit 1
    fi
fi

# Normalize to absolute path
APPS_ROOT="$(cd "$APPS_ROOT" && pwd)"

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

# Create dir if needed
mkdir -p "$TARGET" 2>/dev/null || true

# --- Create config ---
echo ""
log "Creating config at $CONFIG_FILE..."
mkdir -p "$CONFIG_DIR"

cat > "$CONFIG_FILE" << EOF
# Ops Manager Configuration
# Generated: $(date)
environment: $ENV_NAME
apps_root: $APPS_ROOT
project_root: $SCRIPT_DIR

# Service discovery patterns
core_path: _core
services_path: services

# Docker settings
docker_host: unix:///var/run/docker.sock
compose_timeout: 300
EOF

echo "✅ Config saved"

# --- Install ops script ---
echo ""
log "Installing ops to $TARGET..."

OPS_SCRIPT="$TARGET/ops"

# Create ops script with embedded config loader
cat > "$OPS_SCRIPT" << 'OPS_EOF'
#!/bin/bash
set -euo pipefail

# Config locations (in order of priority)
CONFIG_CANDIDATES=(
    "$PWD/.ops-config.yml"
    "$HOME/.config/ops-manager/config.yml"
    "${OPS_CONFIG:-}"
)

CONFIG_FILE=""
for cfg in "${CONFIG_CANDIDATES[@]}"; do
    [[ -n "$cfg" && -f "$cfg" ]] && { CONFIG_FILE="$cfg"; break; }
done

if [[ -z "$CONFIG_FILE" ]]; then
    echo "❌ Config not found. Run ./install.sh first" >&2
    exit 1
fi

# Parse config (simple YAML parser)
parse_config() {
    local key=$1
    grep "^$key:" "$CONFIG_FILE" | cut -d':' -f2- | sed 's/^[[:space:]]*//'
}

APPS_ROOT="$(parse_config "apps_root")"
ENV_TYPE="$(parse_config "environment")"
CORE_PATH="$(parse_config "core_path")"
SERVICES_PATH="$(parse_config "services_path")"

# Verify
[[ -d "$APPS_ROOT" ]] || { echo "❌ Apps root not found: $APPS_ROOT" >&2; exit 1; }

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log() { echo -e "${BLUE}ℹ️  $1${NC}"; }
ok() { echo -e "${GREEN}✅ $1${NC}"; }
err() { echo -e "${RED}❌ $1${NC}" >&2; }

# Service discovery (no cd!)
declare -A SERVICES=()

scan_services() {
    SERVICES=()
    
    # Core services
    local core_dir="$APPS_ROOT/${CORE_PATH:-_core}"
    if [[ -d "$core_dir" ]]; then
        for svc_dir in "$core_dir"/*/; do
            [[ -f "$svc_dir/docker-compose.yml" ]] && SERVICES[$(basename "$svc_dir")]="$svc_dir"
        done
    fi
    
    # Regular services
    local svc_base="$APPS_ROOT/${SERVICES_PATH:-services}"
    for subdir in public internal; do
        local type_dir="$svc_base/$subdir"
        [[ -d "$type_dir" ]] || continue
        for svc_dir in "$type_dir"/*/; do
            [[ -f "$svc_dir/docker-compose.yml" ]] && SERVICES[$(basename "$svc_dir")]="$svc_dir"
        done
    done
}

# Docker compose wrapper (no cd!)
compose_cmd() {
    local svc_dir=$1
    shift
    # Use --project-directory instead of cd
    docker compose --project-directory "$svc_dir" \
                   -f "$svc_dir/docker-compose.yml" \
                   "$@"
}

# Commands
cmd_list() {
    scan_services
    printf "\n%-15s %-50s %s\n" "SERVICE" "PATH" "STATUS"
    printf "%s\n" "--------------------------------------------------------------------------------"
    
    for name in "${!SERVICES[@]}"; do
        local dir="${SERVICES[$name]}"
        local status="stopped"
        
        # Check status without cd
        local running=$(docker compose --project-directory "$dir" -f "$dir/docker-compose.yml" ps -q 2>/dev/null | wc -l)
        [[ "$running" -gt 0 ]] && status="running ($running)"
        
        local short_path="${dir#$APPS_ROOT/}"
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
        # Try as direct path
        for d in "$APPS_ROOT/_core/$svc" "$APPS_ROOT/services/public/$svc" "$APPS_ROOT/services/internal/$svc"; do
            [[ -f "$d/docker-compose.yml" ]] && { dir="$d"; break; }
        done
    fi
    
    [[ -z "$dir" ]] && { err "Service '$svc' not found"; exit 1; }
    
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
        echo "Install lazydocker: go install github.com/jesseduffield/lazydocker@latest"
        exit 1
    fi
    
    if [[ "$target" == "all" ]]; then
        # Create temp config for this session
        local tmp_config=$(mktemp)
        cat > "$tmp_config" << EOF
gui:
  theme:
    activeBorderColor: [green, bold]
    inactiveBorderColor: [white]
customCommands:
  containers:
    - name: reload caddy
      command: 'docker exec caddy caddy reload --config /etc/caddy/Caddyfile'
      attach: false
EOF
        export LAZYDOCKER_CONFIG="$tmp_config"
        cd "$APPS_ROOT" && lazydocker
        rm -f "$tmp_config"
    else
        scan_services
        local dir="${SERVICES[$target]:-}"
        if [[ -n "$dir" ]]; then
            cd "$dir" && lazydocker
        else
            err "Service '$target' not found"
            exit 1
        fi
    fi
}

usage() {
    cat << EOF
Ops Manager (env: $ENV_TYPE)

Usage: ops <command> [args]

Commands:
  list, ls              List all services
  up <svc> [opts]       Start service (opts passed to compose)
  down <svc> [opts]     Stop service
  logs <svc>            Follow logs
  ui [svc|all]          Open lazydocker (default: all)
  reload                Reload Caddy (if running)

Config: $CONFIG_FILE
Apps:   $APPS_ROOT
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
            # Auto-detect: if arg is service name, do 'up'
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

# --- Add to PATH if needed ---
if [[ "$TARGET" == "$HOME/bin" && ":$PATH:" != *":$HOME/bin:"* ]]; then
    echo ""
    echo "⚠️  Add $HOME/bin to your PATH:"
    echo '   echo "export PATH=\"\$HOME/bin:\$PATH\"" >> ~/.bashrc'
    echo '   source ~/.bashrc'
fi

echo ""
echo "🎉 Installation complete!"
echo ""
echo "Quick start:"
echo "  ops list          # Show all services"
echo "  ops up master     # Start master"
echo "  ops ui            # Open lazydocker for all"
echo "  ops ui caddy      # Open lazydocker for caddy only"
echo ""
echo "Config location: $CONFIG_FILE"