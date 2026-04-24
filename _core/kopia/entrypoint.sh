#!/bin/bash
set -euo pipefail

# Idempotent initialization of Kopia repository
# Check if repository already exists
if ! kopia --config-file=/kopia/repository.config repository status 2>/dev/null; then
    echo "Creating new Kopia repository at ${KOPIA_REPOSITORY} (storage type: ${KOPIA_STORAGE_TYPE})"
    # Create repository based on storage type
    case "${KOPIA_STORAGE_TYPE}" in
        filesystem)
            kopia repository create filesystem --path "${KOPIA_REPOSITORY}" --password "${KOPIA_REPOSITORY_PASSWORD}"
            ;;
        s3)
            kopia repository create s3 \
                --bucket "${KOPIA_S3_BUCKET}" \
                --access-key "${AWS_ACCESS_KEY_ID}" \
                --secret-access-key "${AWS_SECRET_ACCESS_KEY}" \
                --region "${AWS_REGION}" \
                --endpoint "${KOPIA_S3_ENDPOINT:-}" \
                --password "${KOPIA_REPOSITORY_PASSWORD}"
            ;;
        sftp)
            kopia repository create sftp \
                --host "${KOPIA_SFTP_HOST}" \
                --port "${KOPIA_SFTP_PORT:-22}" \
                --username "${KOPIA_SFTP_USER}" \
                --password "${KOPIA_SFTP_PASSWORD:-}" \
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

# Generate server password file if not present
if [ ! -f "${KOPIA_SERVER_PASSWORD_FILE}" ]; then
    echo "Generating server password file..."
    echo "${KOPIA_SERVER_PASSWORD:-$KOPIA_REPOSITORY_PASSWORD}" > "${KOPIA_SERVER_PASSWORD_FILE}"
    chmod 600 "${KOPIA_SERVER_PASSWORD_FILE}"
fi

# Start Kopia server
echo "Starting Kopia server on ${KOPIA_SERVER_ADDRESS:-0.0.0.0:51515}"
exec kopia server start \
    --config-file=/kopia/config/repository.config \
    --disable-grpc \
    --address="${KOPIA_SERVER_ADDRESS:-0.0.0.0:51515}" \
    --server-username="${KOPIA_SERVER_USERNAME:-admin}" \
    --server-password-file="${KOPIA_SERVER_PASSWORD_FILE}" \
    --tls-cert-file="${KOPIA_SERVER_CERT_FILE:-}" \
    --tls-key-file="${KOPIA_SERVER_KEY_FILE:-}" \
    --ui-title="Apps Service Backup"