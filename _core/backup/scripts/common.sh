#!/bin/bash
set -euo pipefail

# Common functions for backup scripts

# Logging function
log() {
    local level="$1"
    shift
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] [${level}] $*" >&2
}

# Check if command exists
require_cmd() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        log "ERROR" "Required command '$cmd' not found in PATH"
        exit 1
    fi
}

# Validate environment variables
require_env() {
    local var="$1"
    if [[ -z "${!var:-}" ]]; then
        log "ERROR" "Required environment variable '$var' is not set"
        exit 1
    fi
}

# Create temporary directory with cleanup trap
create_tempdir() {
    local tmpdir
    tmpdir=$(mktemp -d)
    trap "rm -rf '$tmpdir'" EXIT INT TERM
    echo "$tmpdir"
}

# Send notification via ntfy (if configured)
notify() {
    local topic="${NTFY_TOPIC:-backup}"
    local server="${NTFY_SERVER:-http://localhost:8080}"
    local title="$1"
    local message="$2"
    local priority="${3:-default}"

    if [[ -n "${NTFY_ENABLED:-}" && "${NTFY_ENABLED}" = "true" ]]; then
        curl -s -H "Title: $title" -H "Priority: $priority" -d "$message" \
            "${server}/${topic}" >/dev/null 2>&1 || true
    fi
}