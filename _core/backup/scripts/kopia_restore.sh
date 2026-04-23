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
MANIFEST_ID=""
TARGET_DIR=""
RESTORE_DB="${RESTORE_DB:-true}"

# Usage
usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Restore a snapshot using Kopia.

Options:
  --manifest ID         Manifest ID of snapshot to restore (required)
  --target DIR          Target directory for restoration (required)
  --no-db               Skip database restoration
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
  $0 --manifest k123456789 --target /restored/myapp
EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --manifest)
            MANIFEST_ID="$2"
            shift 2
            ;;
        --target)
            TARGET_DIR="$2"
            shift 2
            ;;
        --no-db)
            RESTORE_DB="false"
            shift
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
if [[ -z "$MANIFEST_ID" ]]; then
    log "ERROR" "Manifest ID (--manifest) is required"
    usage
    exit 1
fi
if [[ -z "$TARGET_DIR" ]]; then
    log "ERROR" "Target directory (--target) is required"
    usage
    exit 1
fi
if [[ -e "$TARGET_DIR" && ! -d "$TARGET_DIR" ]]; then
    log "ERROR" "Target path '$TARGET_DIR' exists and is not a directory"
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

# Connect to Kopia server
export KOPIA_PASSWORD="$(cat "$KOPIA_PASSWORD_FILE" 2>/dev/null || echo "$KOPIA_SERVER_PASSWORD")"
KOPIA_SERVER="http://$KOPIA_HOST:$KOPIA_PORT"

log "INFO" "Connecting to Kopia server at $KOPIA_SERVER"
kopia server status --address="$KOPIA_SERVER" --username="$KOPIA_USER" --password="$KOPIA_PASSWORD" || {
    log "ERROR" "Cannot connect to Kopia server"
    notify "Restore Failed" "Cannot connect to Kopia server for manifest $MANIFEST_ID" "high"
    exit 1
}

# Create target directory
mkdir -p "$TARGET_DIR"

# Restore snapshot
log "INFO" "Restoring snapshot $MANIFEST_ID to $TARGET_DIR"
kopia restore "$MANIFEST_ID" "$TARGET_DIR" --password="$KOPIA_REPOSITORY_PASSWORD" || {
    log "ERROR" "Restore failed"
    notify "Restore Failed" "Restore of manifest $MANIFEST_ID failed" "high"
    exit 1
}

# Database restoration (if applicable)
if [[ "$RESTORE_DB" == "true" ]]; then
    if [[ -f "$TARGET_DIR/db/postgres.sql" ]]; then
        log "INFO" "Restoring PostgreSQL database"
        if command -v psql >/dev/null 2>&1 && [[ -n "${PGHOST:-}" ]]; then
            psql -h "${PGHOST:-localhost}" -p "${PGPORT:-5432}" \
                -U "${PGUSER:-postgres}" -d "${PGDATABASE:-postgres}" \
                -f "$TARGET_DIR/db/postgres.sql" 2>/dev/null || {
                log "WARN" "PostgreSQL restore failed"
            }
        else
            log "WARN" "PostgreSQL client not available or connection details missing"
        fi
    fi

    if [[ -f "$TARGET_DIR/db/mysql.sql" ]]; then
        log "INFO" "Restoring MySQL database"
        if command -v mysql >/dev/null 2>&1 && [[ -n "${MYSQL_HOST:-}" ]]; then
            mysql -h "${MYSQL_HOST:-localhost}" -P "${MYSQL_PORT:-3306}" \
                -u "${MYSQL_USER:-root}" -p"${MYSQL_PASSWORD:-}" \
                < "$TARGET_DIR/db/mysql.sql" 2>/dev/null || {
                log "WARN" "MySQL restore failed"
            }
        else
            log "WARN" "MySQL client not available or connection details missing"
        fi
    fi
fi

log "INFO" "Restore completed successfully"
notify "Restore Completed" "Snapshot $MANIFEST_ID restored to $TARGET_DIR" "low"

# Output restored location
echo "$TARGET_DIR"