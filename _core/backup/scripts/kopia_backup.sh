#!/bin/bash
set -euo pipefail

# Source common functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

# Defaults
KOPIA_HOST="${KOPIA_HOST:-localhost}"
KOPIA_PORT="${KOPIA_PORT:-51515}"
KOPIA_USER="${KOPIA_USER:-admin}"
KOPIA_PASSWORD_FILE="${KOPIA_PASSWORD_FILE:-}"
KOPIA_REPOSITORY_PASSWORD="${KOPIA_REPOSITORY_PASSWORD:-}"
BACKUP_SOURCE="${BACKUP_SOURCE:-}"
BACKUP_SERVICE="${BACKUP_SERVICE:-unknown}"
BACKUP_TAGS="${BACKUP_TAGS:-}"
STAGING_DIR=""

# Usage
usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Backup a service using Kopia.

Options:
  --source DIR          Source directory to backup (required)
  --service NAME        Service name (default: unknown)
  --tags TAGS           Comma-separated tags for the snapshot
  --host HOST           Kopia server host (default: localhost)
  --port PORT           Kopia server port (default: 51515)
  --user USER           Kopia server username (default: admin)
  --password-file FILE  File containing Kopia server password
  --repository-password PASSWORD  Repository password
  --help                Show this help

Environment variables:
  KOPIA_REPOSITORY_PASSWORD  Repository password (required)
  KOPIA_SERVER_PASSWORD      Server password (alternative to password-file)
  NTFY_ENABLED               Enable notifications (true/false)
  NTFY_SERVER                ntfy server URL
  NTFY_TOPIC                 ntfy topic

Example:
  $0 --source /services/myapp --service myapp --tags daily,full
EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --source)
            BACKUP_SOURCE="$2"
            shift 2
            ;;
        --service)
            BACKUP_SERVICE="$2"
            shift 2
            ;;
        --tags)
            BACKUP_TAGS="$2"
            shift 2
            ;;
        --host)
            KOPIA_HOST="$2"
            shift 2
            ;;
        --port)
            KOPIA_PORT="$2"
            shift 2
            ;;
        --user)
            KOPIA_USER="$2"
            shift 2
            ;;
        --password-file)
            KOPIA_PASSWORD_FILE="$2"
            shift 2
            ;;
        --repository-password)
            KOPIA_REPOSITORY_PASSWORD="$2"
            shift 2
            ;;
        --help)
            usage
            exit 0
            ;;
        *)
            log "ERROR" "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Validate inputs
require_env "KOPIA_REPOSITORY_PASSWORD"
if [[ -z "$BACKUP_SOURCE" ]]; then
    log "ERROR" "Backup source (--source) is required"
    usage
    exit 1
fi
if [[ ! -d "$BACKUP_SOURCE" ]]; then
    log "ERROR" "Source directory '$BACKUP_SOURCE' does not exist"
    exit 1
fi

# Determine password file
if [[ -z "$KOPIA_PASSWORD_FILE" ]]; then
    if [[ -n "${KOPIA_SERVER_PASSWORD:-}" ]]; then
        KOPIA_PASSWORD_FILE="<(echo \"$KOPIA_SERVER_PASSWORD\")"
    else
        log "ERROR" "Either --password-file or KOPIA_SERVER_PASSWORD must be set"
        exit 1
    fi
fi

# Create staging directory
STAGING_DIR=$(create_tempdir)
log "INFO" "Staging directory: $STAGING_DIR"

# Database dump (if applicable)
if command -v pg_dump >/dev/null 2>&1 && [[ -n "${PGHOST:-}" ]]; then
    log "INFO" "Creating PostgreSQL dump"
    mkdir -p "$STAGING_DIR/db"
    pg_dump --clean --if-exists --no-owner --no-privileges \
        -h "${PGHOST:-localhost}" -p "${PGPORT:-5432}" \
        -U "${PGUSER:-postgres}" -d "${PGDATABASE:-postgres}" \
        > "$STAGING_DIR/db/postgres.sql" 2>/dev/null || {
        log "WARN" "PostgreSQL dump failed, skipping"
        rm -f "$STAGING_DIR/db/postgres.sql"
    }
fi

if command -v mysqldump >/dev/null 2>&1 && [[ -n "${MYSQL_HOST:-}" ]]; then
    log "INFO" "Creating MySQL dump"
    mkdir -p "$STAGING_DIR/db"
    mysqldump -h "${MYSQL_HOST:-localhost}" -P "${MYSQL_PORT:-3306}" \
        -u "${MYSQL_USER:-root}" -p"${MYSQL_PASSWORD:-}" \
        --all-databases --single-transaction --routines --triggers \
        > "$STAGING_DIR/db/mysql.sql" 2>/dev/null || {
        log "WARN" "MySQL dump failed, skipping"
        rm -f "$STAGING_DIR/db/mysql.sql"
    }
fi

# Filesystem copy using rsync (preserve permissions, exclude .git, node_modules, etc.)
log "INFO" "Copying files from $BACKUP_SOURCE to staging"
rsync -a --delete \
    --exclude='.git' \
    --exclude='node_modules' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.venv' \
    --exclude='venv' \
    --exclude='.env' \
    --exclude='*.log' \
    --exclude='*.tmp' \
    --exclude='*.temp' \
    "$BACKUP_SOURCE/" "$STAGING_DIR/fs/" 2>/dev/null || true

# Connect to Kopia server
export KOPIA_PASSWORD="$(cat "$KOPIA_PASSWORD_FILE" 2>/dev/null || echo "$KOPIA_SERVER_PASSWORD")"
KOPIA_SERVER="http://$KOPIA_HOST:$KOPIA_PORT"

log "INFO" "Connecting to Kopia server at $KOPIA_SERVER"
kopia server status --address="$KOPIA_SERVER" --username="$KOPIA_USER" --password="$KOPIA_PASSWORD" || {
    log "ERROR" "Cannot connect to Kopia server"
    notify "Backup Failed" "Cannot connect to Kopia server for service $BACKUP_SERVICE" "high"
    exit 1
}

# Create snapshot
log "INFO" "Creating snapshot for service $BACKUP_SERVICE"
TAG_ARGS=""
if [[ -n "$BACKUP_TAGS" ]]; then
    IFS=',' read -ra TAGS <<< "$BACKUP_TAGS"
    for tag in "${TAGS[@]}"; do
        TAG_ARGS="$TAG_ARGS --tag $tag"
    done
fi

MANIFEST_ID=$(kopia snapshot create "$STAGING_DIR" \
    --host "$BACKUP_SERVICE" \
    $TAG_ARGS \
    --password="$KOPIA_REPOSITORY_PASSWORD" \
    --json | jq -r '.rootEntry.manifestID')

if [[ -z "$MANIFEST_ID" || "$MANIFEST_ID" == "null" ]]; then
    log "ERROR" "Failed to create snapshot"
    notify "Backup Failed" "Snapshot creation failed for service $BACKUP_SERVICE" "high"
    exit 1
fi

log "INFO" "Snapshot created with manifest ID: $MANIFEST_ID"
echo "$MANIFEST_ID"

# Send success notification
notify "Backup Completed" "Service $BACKUP_SERVICE backed up successfully (ID: $MANIFEST_ID)" "low"

log "INFO" "Backup completed successfully"