#!/bin/bash
set -euo pipefail

# Инициализация Kopia-репозитория (идемпотентно) и запуск сервера.
#
# ВАЖНО: create/status/server используют ОДИН И ТОТ ЖЕ config-файл, иначе
# репозиторий создаётся в одном месте, а сервер стартует с пустым конфигом.

CONFIG="${KOPIA_CONFIG_FILE:-/kopia/config/repository.config}"

: "${KOPIA_REPOSITORY_PASSWORD:?KOPIA_REPOSITORY_PASSWORD обязателен — заполните .env (см. .env.example)}"
: "${KOPIA_REPOSITORY:=/repository}"
: "${KOPIA_STORAGE_TYPE:=filesystem}"

# kopia CLI читает пароль репозитория из KOPIA_PASSWORD (не из
# KOPIA_REPOSITORY_PASSWORD). Без экспорта status/create уходят в интерактивный
# запрос пароля и падают в неинтерактивном окружении.
export KOPIA_PASSWORD="${KOPIA_REPOSITORY_PASSWORD}"

mkdir -p "$(dirname "$CONFIG")"

# Idempotent initialization of Kopia repository
if ! kopia --config-file="$CONFIG" repository status >/dev/null 2>&1; then
    echo "Creating new Kopia repository at ${KOPIA_REPOSITORY} (storage type: ${KOPIA_STORAGE_TYPE})"
    case "${KOPIA_STORAGE_TYPE}" in
        filesystem)
            kopia --config-file="$CONFIG" repository create filesystem \
                --path "${KOPIA_REPOSITORY}" \
                --password "${KOPIA_REPOSITORY_PASSWORD}"
            ;;
        s3)
            kopia --config-file="$CONFIG" repository create s3 \
                --bucket "${KOPIA_S3_BUCKET}" \
                --access-key "${AWS_ACCESS_KEY_ID}" \
                --secret-access-key "${AWS_SECRET_ACCESS_KEY}" \
                --region "${AWS_REGION}" \
                --endpoint "${KOPIA_S3_ENDPOINT:-}" \
                --password "${KOPIA_REPOSITORY_PASSWORD}"
            ;;
        sftp)
            kopia --config-file="$CONFIG" repository create sftp \
                --host "${KOPIA_SFTP_HOST}" \
                --port "${KOPIA_SFTP_PORT:-22}" \
                --username "${KOPIA_SFTP_USER}" \
                --keyfile "${KOPIA_SFTP_KEYFILE:-}" \
                --path "${KOPIA_SFTP_PATH}" \
                --password "${KOPIA_REPOSITORY_PASSWORD}"
            ;;
        *)
            echo "Unsupported storage type: ${KOPIA_STORAGE_TYPE}"
            exit 1
            ;;
    esac
    echo "Repository created successfully."
else
    echo "Repository already exists, skipping creation."
fi

# Ensure proper ownership for repository and config directories
chown -R 1000:1000 /repository /kopia 2>/dev/null || true

# Generate server password file if not present (файл нужен клиентам/скриптам)
if [ ! -f "${KOPIA_SERVER_PASSWORD_FILE}" ]; then
    echo "Generating server password file..."
    echo "${KOPIA_SERVER_PASSWORD:-$KOPIA_REPOSITORY_PASSWORD}" > "${KOPIA_SERVER_PASSWORD_FILE}"
    chmod 600 "${KOPIA_SERVER_PASSWORD_FILE}"
fi

# Пароль HTTP basic auth для kopia server: в новых версиях kopia берётся из
# KOPIA_SERVER_PASSWORD (флаг --server-password-file удалён)
export KOPIA_SERVER_PASSWORD="${KOPIA_SERVER_PASSWORD:-$KOPIA_REPOSITORY_PASSWORD}"

# Start Kopia server
SERVER_ADDR="${KOPIA_SERVER_ADDRESS:-http://0.0.0.0:51515}"
echo "Starting Kopia server on ${SERVER_ADDR}"
SERVER_ARGS=(
    server start
    --config-file="$CONFIG"
    --address="$SERVER_ADDR"
    --server-username="${KOPIA_SERVER_USERNAME:-admin}"
)
# TLS опционально: пустые пути не передаём (иначе kopia падает с ошибкой).
# Без TLS сервер работает по HTTP только с явным --insecure (допустимо:
# трафик внутри docker-сети platform_network, порт наружу не публикуется).
if [ -n "${KOPIA_SERVER_CERT_FILE:-}" ]; then
    SERVER_ARGS+=(--tls-cert-file="${KOPIA_SERVER_CERT_FILE}")
    [ -n "${KOPIA_SERVER_KEY_FILE:-}" ] && SERVER_ARGS+=(--tls-key-file="${KOPIA_SERVER_KEY_FILE}")
else
    SERVER_ARGS+=(--insecure)
fi
exec kopia "${SERVER_ARGS[@]}"
