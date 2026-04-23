#!/bin/bash
# Test environment for backup system (gitignored)
# This file is for local testing only, not committed to repository.

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Backup System Test Environment ===${NC}"

# Check dependencies
echo "Checking dependencies..."
for cmd in docker docker-compose jq curl rsync; do
    if command -v "$cmd" >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} $cmd"
    else
        echo -e "  ${RED}✗${NC} $cmd (missing)"
    fi
done

# Load environment
if [[ -f "_core/kopia/.env" ]]; then
    echo "Loading Kopia environment from _core/kopia/.env"
    source "_core/kopia/.env"
elif [[ -f "_core/kopia/.env.example" ]]; then
    echo "Using example environment (please copy .env.example to .env)"
    export KOPIA_REPOSITORY_PASSWORD="testpassword"
    export KOPIA_SERVER_PASSWORD="testpassword"
else
    echo "No environment file found"
fi

# Set defaults
export KOPIA_HOST="${KOPIA_HOST:-localhost}"
export KOPIA_PORT="${KOPIA_PORT:-51515}"
export KOPIA_USER="${KOPIA_USER:-admin}"
export NTFY_ENABLED="${NTFY_ENABLED:-false}"
export BACKUP_SOURCE="${BACKUP_SOURCE:-./test-backup-source}"
export BACKUP_SERVICE="${BACKUP_SERVICE:-test-service}"

# Create test source directory
echo "Creating test source directory..."
mkdir -p "$BACKUP_SOURCE"
echo "Test file created at $(date)" > "$BACKUP_SOURCE/test.txt"
mkdir -p "$BACKUP_SOURCE/subdir"
echo "Another test file" > "$BACKUP_SOURCE/subdir/another.txt"

# Function to start services
start_services() {
    echo -e "\n${YELLOW}Starting Kopia and ntfy services...${NC}"
    
    # Create network if not exists
    if ! docker network ls | grep -q apps-service-net; then
        docker network create apps-service-net
    fi
    
    # Start Kopia
    cd _core/kopia
    docker-compose up -d
    sleep 5
    cd - >/dev/null
    
    # Start ntfy
    cd _core/monitoring/ntfy
    docker-compose up -d
    sleep 3
    cd - >/dev/null
    
    echo "Services started."
}

# Function to stop services
stop_services() {
    echo -e "\n${YELLOW}Stopping services...${NC}"
    cd _core/kopia && docker-compose down
    cd - >/dev/null
    cd _core/monitoring/ntfy && docker-compose down
    cd - >/dev/null
}

# Function to test backup
test_backup() {
    echo -e "\n${YELLOW}Testing backup...${NC}"
    local manifest_id
    manifest_id=$(_core/backup/scripts/kopia_backup.sh \
        --source "$BACKUP_SOURCE" \
        --service "$BACKUP_SERVICE" \
        --tags "test,automated" \
        --host "$KOPIA_HOST" \
        --port "$KOPIA_PORT" \
        --user "$KOPIA_USER" \
        --repository-password "$KOPIA_REPOSITORY_PASSWORD" 2>&1 | tail -1)
    
    if [[ "$manifest_id" =~ ^k[0-9a-f]+$ ]]; then
        echo -e "${GREEN}Backup successful! Manifest ID: $manifest_id${NC}"
        echo "$manifest_id" > /tmp/test_manifest_id.txt
    else
        echo -e "${RED}Backup failed${NC}"
        return 1
    fi
}

# Function to test restore
test_restore() {
    echo -e "\n${YELLOW}Testing restore...${NC}"
    local manifest_id
    manifest_id=$(cat /tmp/test_manifest_id.txt 2>/dev/null || echo "")
    if [[ -z "$manifest_id" ]]; then
        echo "No manifest ID found, running backup first"
        test_backup
        manifest_id=$(cat /tmp/test_manifest_id.txt)
    fi
    
    local restore_dir="./test-restore-$(date +%s)"
    _core/backup/scripts/kopia_restore.sh \
        --manifest "$manifest_id" \
        --target "$restore_dir" \
        --host "$KOPIA_HOST" \
        --port "$KOPIA_PORT" \
        --user "$KOPIA_USER" \
        --repository-password "$KOPIA_REPOSITORY_PASSWORD"
    
    if [[ -f "$restore_dir/test.txt" ]]; then
        echo -e "${GREEN}Restore successful! Files restored to: $restore_dir${NC}"
    else
        echo -e "${RED}Restore failed${NC}"
        return 1
    fi
}

# Function to test policy
test_policy() {
    echo -e "\n${YELLOW}Testing policy...${NC}"
    _core/backup/scripts/kopia_policy.sh \
        --host "$BACKUP_SERVICE" \
        --keep-daily 5 \
        --keep-weekly 2 \
        --host "$KOPIA_HOST" \
        --port "$KOPIA_PORT" \
        --user "$KOPIA_USER" \
        --repository-password "$KOPIA_REPOSITORY_PASSWORD"
}

# Function to clean up
cleanup() {
    echo -e "\n${YELLOW}Cleaning up...${NC}"
    rm -rf "$BACKUP_SOURCE" ./test-restore-* /tmp/test_manifest_id.txt 2>/dev/null || true
}

# Main menu
while true; do
    echo -e "\n${YELLOW}Test Menu:${NC}"
    echo "1) Start services"
    echo "2) Test backup"
    echo "3) Test restore"
    echo "4) Test policy"
    echo "5) Run all tests"
    echo "6) Stop services"
    echo "7) Clean up test files"
    echo "8) Exit"
    read -p "Select option: " choice
    
    case $choice in
        1) start_services ;;
        2) test_backup ;;
        3) test_restore ;;
        4) test_policy ;;
        5)
            start_services
            test_backup
            test_restore
            test_policy
            ;;
        6) stop_services ;;
        7) cleanup ;;
        8) break ;;
        *) echo "Invalid option" ;;
    esac
done

echo -e "${GREEN}Test completed.${NC}"
cleanup
stop_services