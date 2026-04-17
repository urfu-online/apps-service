#!/bin/bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
ENV_FILE="$PROJECT_ROOT/.env"

# Важно: используем `--env-file` с абсолютным путём (если .env существует), чтобы интерполяция
# ${VAR:-default} работала стабильно независимо от текущей директории запуска.
COMPOSE_ARGS=()
if [[ -f "$ENV_FILE" ]]; then
    COMPOSE_ARGS+=(--env-file "$ENV_FILE")
else
    warn ".env not found at $ENV_FILE; continuing without --env-file"
fi

check_directory() {
    if [[ ! -d "$PROJECT_ROOT/_core" ]] || [[ ! -d "$PROJECT_ROOT/services" ]]; then
        error "This script must be run from the project root where _core and services directories exist."
        exit 1
    fi
}

create_backups() {
    log "Creating backups..."
    
    # Stop master temporarily for consistent backup
    log "Stopping master service..."
    docker compose "${COMPOSE_ARGS[@]}" -f "$PROJECT_ROOT/_core/master/docker-compose.yml" down || warn "Failed to stop master service"

    # Backup database
    DB_PATH="$PROJECT_ROOT/_core/master/master.db"
    if [[ -f "$DB_PATH" ]]; then
        BACKUP_DB_NAME="/tmp/master.db.backup.$(date +%Y%m%d_%H%M%S)"
        log "Backing up database to $BACKUP_DB_NAME..."
        cp "$DB_PATH" "$BACKUP_DB_NAME" || warn "Failed to backup master.db"
    else
        warn "Database file not found at $DB_PATH, skipping backup"
    fi

    # Backup services (исключаем директории, требующие root)
    SERVICES_BACKUP="/tmp/services-backup.$(date +%Y%m%d_%H%M%S).tgz"
    log "Backing up services to $SERVICES_BACKUP..."
    tar --exclude='*/postgres/data' \
        --exclude='*/node_modules' \
        --exclude='*/.git' \
        --exclude='*/__pycache__' \
        czf "$SERVICES_BACKUP" services/ 2>/dev/null || warn "tar finished with warnings (some dirs skipped)"

    # Backup Caddy configuration
    CADDY_BACKUP="/tmp/caddy-backup.$(date +%Y%m%d_%H%M%S).tgz"
    log "Backing up Caddy config to $CADDY_BACKUP..."
    tar czf "$CADDY_BACKUP" -C "$PROJECT_ROOT" _core/caddy/ 2>/dev/null || warn "Caddy backup warning"

    log "Verifying backup files..."
    ls -lh /tmp/*.backup.* /tmp/*.tgz 2>/dev/null || true

    log "Restarting master service..."
    "$PROJECT_ROOT/restart_core.sh" || error "Failed to restart core services"
}

pull_latest_code() {
    log "Pulling latest code..."
    cd "$PROJECT_ROOT"
    if ! git status --porcelain | grep -q .; then
        log "No local changes detected"
    else
        warn "Local changes detected:"
        git status --short
        log "Stashing local changes..."
        git stash
    fi
    git fetch origin main
    git pull origin main
    log "Successfully pulled latest code"
    log "Last commits:"
    git log --oneline -5
}

restart_core() {
    log "Restarting core services..."
    "$PROJECT_ROOT/restart_core.sh" --build
    log "Checking if services are running..."
    docker ps --filter "status=running" --format "table {{.Names}}\t{{.Status}}" | grep -E "(master|caddy)" || warn "Core services not detected"
}

verify_update() {
    log "Verifying the update..."
    MASTER_HEALTH_URL="http://localhost:8001/healthz"
    log "Checking master health at $MASTER_HEALTH_URL..."
    MASTER_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$MASTER_HEALTH_URL") || warn "Master health check failed"
    [[ "$MASTER_STATUS" =~ ^20[0-9]$ ]] && log "Master health check OK (Status: $MASTER_STATUS)" || warn "Master health check failed (Status: $MASTER_STATUS)"

    WEB_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost/") || warn "Web check failed"
    [[ "$WEB_STATUS" =~ ^20[0-9]$ ]] && log "Web endpoint accessible (Status: $WEB_STATUS)" || warn "Web endpoint not accessible (Status: $WEB_STATUS)"

    log "Checking master logs..."
    docker logs platform-master --tail 50 || warn "Could not fetch master logs"
}

show_checklist() {
    log "Update completed. Remember to check:"
    echo "
- ${YELLOW}[ ]${NC} Confirm all services are running properly
- ${YELLOW}[ ]${NC} Verify key functionalities
- ${YELLOW}[ ]${NC} Monitor logs for any unusual activity
"
}

main() {
    log "Starting platform update process..."
    check_directory
    echo -e "${YELLOW}"
    read -p "This script will update the platform and take backups. Continue? [y/N]: " -n 1 -r REPLY
    echo -e "${NC}"
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then error "Update cancelled."; exit 1; fi

    create_backups
    pull_latest_code
    restart_core
    verify_update
    show_checklist
    log "Platform update process completed!"
}

usage() { echo "Usage: $0"; exit 0; }
case "${1:-}" in
    -h|--help) usage ;;
    *) main ;;
esac
