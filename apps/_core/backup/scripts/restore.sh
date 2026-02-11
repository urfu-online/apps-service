#!/bin/bash

# Скрипт для восстановления бэкапа с помощью Restic

set -e

# Параметры
SNAPSHOT_ID=$1
RESTORE_PATH=$2

if [ -z "$SNAPSHOT_ID" ] || [ -z "$RESTORE_PATH" ]; then
  echo "Usage: $0 <snapshot_id> <restore_path>"
  exit 1
fi

echo "Starting restore from snapshot: $SNAPSHOT_ID"
echo "Restore path: $RESTORE_PATH"

# Проверка существования снимка
if ! restic snapshots "$SNAPSHOT_ID" >/dev/null 2>&1; then
  echo "Snapshot $SNAPSHOT_ID not found"
  exit 1
fi

# Восстановление
echo "Restoring snapshot..."
restic restore "$SNAPSHOT_ID" --target "$RESTORE_PATH"

# Проверка результата
if [ $? -eq 0 ]; then
  echo "Restore completed successfully"
  exit 0
else
  echo "Restore failed"
  exit 1
fi