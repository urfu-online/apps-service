#!/bin/bash

# Platform Update Script
# Based on the deployment runbook
# Execute this script in the /apps folder on production

set -e  # Exit on any error

# Color codes for output formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in the right directory
check_directory() {
    if [[ ! -d "_core" ]] || [[ ! -d "services" ]]; then
        error "This script must be run from the /apps folder where _core and services directories exist."
        exit 1
    fi
}

# Create backups of important data
create_backups() {
    log "Creating backups..."
    
    # Stop master temporarily for consistent backup
    log "Stopping master service..."
    docker compose -f _core/master/docker-compose.yml down || warn "Failed to stop master service"
    
    # Backup database
    DB_PATH="_core/master/master.db"
    if [[ -f "$DB_PATH" ]]; then
        BACKUP_DB_NAME="/tmp/master.db.backup.$(date +%Y%m%d_%H%M%S)"
        log "Backing up database to $BACKUP_DB_NAME..."
        cp "$DB_PATH" "$BACKUP_DB_NAME"
        log "Database backup created: $BACKUP_DB_NAME"
    else
        warn "Database file not found at $DB_PATH, skipping backup"
    fi
    
    # Backup services configurations
    SERVICES_BACKUP="/tmp/services-backup.$(date +%Y%m%d_%H%M%S).tgz"
    log "Backing up services to $SERVICES_BACKUP..."
    tar czf "$SERVICES_BACKUP" services/
    log "Services backup created: $SERVICES_BACKUP"
    
    # Backup Caddy configuration
    CADDY_BACKUP="/tmp/caddy-backup.$(date +%Y%m%d_%H%M%S).tgz"
    log "Backing up Caddy config to $CADDY_BACKUP..."
    tar czf "$CADDY_BACKUP" _core/caddy/
    log "Caddy backup created: $CADDY_BACKUP"
    
    # Show backup files
    log "Verifying backup files..."
    ls -lh /tmp/*.backup.* /tmp/*.tgz
    
    # Save the current service list
    SERVICE_LIST="/tmp/services-before-$(date +%Y%m%d_%H%M%S).txt"
    log "Recording list of current services to $SERVICE_LIST..."
    if command -v ops &> /dev/null; then
        ops list > "$SERVICE_LIST"
    else
        # Fallback to docker commands if ops is not available
        docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" > "$SERVICE_LIST"
    fi
    log "Current service list recorded"
    
    # Restart master
    log "Restarting master service..."
    ./restart_core.sh || error "Failed to restart core services"
}

# Pull the latest code
pull_latest_code() {
    log "Pulling latest code..."
    
    # Check for local changes
    if ! git status --porcelain | grep -q .; then
        log "No local changes detected"
    else
        warn "Local changes detected:"
        git status --short
        log "Stashing local changes..."
        git stash
    fi
    
    # Pull the latest code
    log "Fetching and merging latest code..."
    git fetch origin main
    git pull origin main
    
    log "Successfully pulled latest code"
    log "Last commits:"
    git log --oneline -5
}

# Restart the core services
restart_core() {
    log "Restarting core services..."
    
    # Rebuild and restart with the new code
    ./restart_core.sh --build
    
    log "Checking if services are running..."
    RUNNING_SERVICES=$(docker ps --filter "status=running" --format "table {{.Names}}\t{{.Status}}" | grep -E "(master|caddy)")
    if [[ -n "$RUNNING_SERVICES" ]]; then
        log "Core services running:"
        echo "$RUNNING_SERVICES"
    else
        error "No core services appear to be running!"
    fi
}

# Verify the update
verify_update() {
    log "Verifying the update..."
    
    # Check master health
    MASTER_HEALTH_URL="http://localhost:8001/healthz"
    log "Checking master health at $MASTER_HEALTH_URL..."
    MASTER_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$MASTER_HEALTH_URL") || warn "Master health check failed"
    if [[ "$MASTER_STATUS" =~ ^20[0-9]$ ]]; then
        log "Master health check OK (Status: $MASTER_STATUS)"
    else
        warn "Master health check failed (Status: $MASTER_STATUS)"
    fi
    
    # Check web endpoint
    WEB_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost/") || warn "Web check failed"
    if [[ "$WEB_STATUS" =~ ^20[0-9]$ ]]; then
        log "Web endpoint accessible (Status: $WEB_STATUS)"
    else
        warn "Web endpoint not accessible (Status: $WEB_STATUS)"
    fi
    
    # Show last 50 lines of master logs
    log "Checking master logs..."
    docker logs platform-master --tail 50 || warn "Could not fetch master logs"
    
    # List running services
    log "Listing running services..."
    if command -v ops &> /dev/null; then
        ops list || warn "Failed to list services using ops"
    else
        docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
    fi
}

# Display checklist
show_checklist() {
    log "Update completed. Remember to check:"
    echo "
    - ${YELLOW}[ ]${NC} Confirm all services are running properly
    - ${YELLOW}[ ]${NC} Verify key functionalities
    - ${YELLOW}[ ]${NC} Test critical business operations
    - ${YELLOW}[ ]${NC} Monitor logs for any unusual activity
    - ${YELLOW}[ ]${NC} Ensure Telegram notifications are working
    "
}

# Main function
main() {
    log "Starting platform update process..."
    
    check_directory
    
    # Prompt user to confirm before proceeding with destructive changes
    echo -e "${YELLOW}"
    read -p "This script will update the platform and take backups. Continue? [y/N]: " -n 1 -r REPLY
    echo -e "${NC}"
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        error "Update cancelled."
        exit 1
    fi
    
    create_backups
    pull_latest_code
    restart_core
    verify_update
    show_checklist
    
    log "Platform update process completed!"
    log "If any issues occur, use the backup files in /tmp/ to restore."
}

# Print usage information
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help     Show this help message"
    echo "  --dry-run      Perform a dry run without making changes"
    echo ""
    echo "Warning: This script performs system updates and creates backups."
    echo "Run it from the /apps folder on production server."
}

# Parse command line arguments
DRY_RUN=false
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        -h|--help)
            usage
            exit 0
            ;;
        --dry-run)
            DRY_RUN=true
            echo "Dry run mode: no actual changes will be made"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

if [[ "$DRY_RUN" == true ]]; then
    log "Running in dry-run mode. No changes will be made."
    exit 0
else
    main
fi