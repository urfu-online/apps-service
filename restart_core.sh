#!/bin/bash
set -euo pipefail

# Определяем корень проекта и .env независимо от CWD
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
ENV_FILE="$PROJECT_ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo -e "\033[0;31m❌ .env not found at $ENV_FILE\033[0m"
    exit 1
fi

COMPOSE_ARGS="--env-file $ENV_FILE"

usage() {
    echo "Usage: $0 [--build]"
    echo "  --build    Rebuild images before starting"
    exit 1
}

BUILD_FLAG=""
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --build) BUILD_FLAG="--build" ;;
        -h|--help) usage ;;
        *) echo "Unknown parameter: $1"; usage ;;
    esac
    shift
done

echo "🛑 Stopping Master service..."
docker compose $COMPOSE_ARGS -f "$PROJECT_ROOT/_core/master/docker-compose.yml" down

echo "🚀 Starting Master service..."
docker compose $COMPOSE_ARGS -f "$PROJECT_ROOT/_core/master/docker-compose.yml" up -d $BUILD_FLAG

echo "🛑 Stopping Caddy..."
docker compose $COMPOSE_ARGS -f "$PROJECT_ROOT/_core/caddy/docker-compose.yml" down

echo "🌐 Starting Caddy..."
docker compose $COMPOSE_ARGS -f "$PROJECT_ROOT/_core/caddy/docker-compose.yml" up -d $BUILD_FLAG

echo "✅ Core services restarted successfully."