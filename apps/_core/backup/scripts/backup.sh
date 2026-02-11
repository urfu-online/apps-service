#!/bin/bash

# Скрипт для создания бэкапа с помощью Restic

set -e

# Параметры
SERVICE_NAME=$1
BACKUP_PATH=$2

if [ -z "$SERVICE_NAME" ] || [ -z "$BACKUP_PATH" ]; then
  echo "Usage: $0 <service_name> <backup_path>"
  exit 1
fi

echo "Starting backup for service: $SERVICE_NAME"
echo "Backup path: $BACKUP_PATH"

# Инициализация репозитория, если нужно
if ! restic snapshots >/dev/null 2>&1; then
  echo "Initializing restic repository..."
  restic init
fi

# Создание бэкапа
echo "Creating backup..."
restic backup "$BACKUP_PATH" --tag "service:$SERVICE_NAME" --tag "manual"

# Проверка результата
if [ $? -eq 0 ]; then
  echo "Backup completed successfully"
  
  # Вывод информации о последнем снимке
  echo "Latest snapshot:"
  restic snapshots --last --json
  
  exit 0
else
  echo "Backup failed"
  exit 1
fi