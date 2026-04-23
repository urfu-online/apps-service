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
POLICY_HOST="${POLICY_HOST:-}"
KEEP_HOURLY="${KEEP_HOURLY:-0}"
KEEP_DAILY="${KEEP_DAILY:-7}"
KEEP_WEEKLY="${KEEP_WEEKLY:-4}"
KEEP_MONTHLY="${KEEP_MONTHLY:-12}"
KEEP_YEARLY="${KEEP_YEARLY:-3}"

# Usage
usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Set retention policy for Kopia snapshots.

Options:
  --host HOST           Host filter (service name) - apply to all if empty
  --keep-hourly N       Keep N hourly snapshots (default: 0)
  --keep-daily N        Keep N daily snapshots (default: 7)
  --keep-weekly N       Keep N weekly snapshots (default: 4)
  --keep-monthly N      Keep N monthly snapshots (default: 12)
  --keep-yearly N       Keep N yearly snapshots (default: 3)
  --host HOST           Kopia server host (default: localhost)
  --port PORT           Kopia server port (default: 51515)
  --user USER           Kopia server username (default: admin)
  --password-file FILE  File containing Kopia server password
  --repository-password PASSWORD  Repository password
  --help                Show this help

Environment variables:
  KOPIA_REPOSITORY_PASSWORD  Repository password (required)
  KOPIA_SERVER_PASSWORD      Server password (alternative to password-file)

Example:
  $0 --host myapp --keep-daily 30 --keep-weekly 8
EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)
            POLICY_HOST="$2"
            shift 2
            ;;
        --keep-hourly)
            KEEP_HOURLY="$2"
            shift 2
            ;;
        --keep-daily)
            KEEP_DAILY="$2"
            shift 2
            ;;
        --keep-weekly)
            KEEP_WEEKLY="$2"
            shift 2
            ;;
        --keep-monthly)
            KEEP_MONTHLY="$2"
            shift 2
            ;;
        --keep-yearly)
            KEEP_YEARLY="$2"
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
    exit 1
}

# Build policy command
POLICY_CMD="kopia policy set"
if [[ -n "$POLICY_HOST" ]]; then
    POLICY_CMD="$POLICY_CMD --host \"$POLICY_HOST\""
fi

POLICY_CMD="$POLICY_CMD \
    --keep-hourly \"$KEEP_HOURLY\" \
    --keep-daily \"$KEEP_DAILY\" \
    --keep-weekly \"$KEEP_WEEKLY\" \
    --keep-monthly \"$KEEP_MONTHLY\" \
    --keep-yearly \"$KEEP_YEARLY\" \
    --password \"$KOPIA_REPOSITORY_PASSWORD\""

# Apply policy
log "INFO" "Setting retention policy"
if [[ -n "$POLICY_HOST" ]]; then
    log "INFO" "Target host: $POLICY_HOST"
fi
log "INFO" "Retention: hourly=$KEEP_HOURLY, daily=$KEEP_DAILY, weekly=$KEEP_WEEKLY, monthly=$KEEP_MONTHLY, yearly=$KEEP_YEARLY"

eval "$POLICY_CMD" || {
    log "ERROR" "Failed to set policy"
    exit 1
}

log "INFO" "Policy applied successfully"

# Show current policy
log "INFO" "Current policy:"
kopia policy show --password="$KOPIA_REPOSITORY_PASSWORD"