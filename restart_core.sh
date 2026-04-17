#!/bin/bash
set -euo pipefail

# Определяем корень проекта и .env независимо от CWD
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
ENV_FILE="$PROJECT_ROOT/.env"

# Важно: используем `--env-file` с абсолютным путём (если .env существует), чтобы интерполяция
# ${VAR:-default} работала стабильно независимо от текущей директории запуска.
COMPOSE_ARGS=()
if [[ -f "$ENV_FILE" ]]; then
    COMPOSE_ARGS+=(--env-file "$ENV_FILE")
else
    echo "WARNING: .env not found at $ENV_FILE; continuing without --env-file" >&2
fi

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
docker compose "${COMPOSE_ARGS[@]}" -f "$PROJECT_ROOT/_core/master/docker-compose.yml" down

echo "🚀 Starting Master service..."
docker compose "${COMPOSE_ARGS[@]}" -f "$PROJECT_ROOT/_core/master/docker-compose.yml" up -d $BUILD_FLAG

echo "🛑 Stopping Caddy..."
docker compose "${COMPOSE_ARGS[@]}" -f "$PROJECT_ROOT/_core/caddy/docker-compose.yml" down

echo "🌐 Starting Caddy..."
docker compose "${COMPOSE_ARGS[@]}" -f "$PROJECT_ROOT/_core/caddy/docker-compose.yml" up -d $BUILD_FLAG

echo "✅ Core services restarted successfully."
