#!/bin/bash

# Скрипт для очистки старых бэкапов с помощью Restic

set -e

# Параметры по умолчанию
KEEP_LAST=10
KEEP_DAILY=7
KEEP_WEEKLY=4
KEEP_MONTHLY=12
KEEP_YEARLY=3

# Парсинг аргументов
while [[ $# -gt 0 ]]; do
  case $1 in
    --keep-last)
      KEEP_LAST="$2"
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
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

echo "Starting cleanup with policy:"
echo "  Keep last: $KEEP_LAST"
echo "  Keep daily: $KEEP_DAILY"
echo "  Keep weekly: $KEEP_WEEKLY"
echo "  Keep monthly: $KEEP_MONTHLY"
echo "  Keep yearly: $KEEP_YEARLY"

# Очистка старых снимков
echo "Cleaning up old snapshots..."
restic forget --prune \
  --keep-last "$KEEP_LAST" \
  --keep-daily "$KEEP_DAILY" \
  --keep-weekly "$KEEP_WEEKLY" \
  --keep-monthly "$KEEP_MONTHLY" \
  --keep-yearly "$KEEP_YEARLY"

# Проверка результата
if [ $? -eq 0 ]; then
  echo "Cleanup completed successfully"
  
  # Вывод информации о сохраненных снимках
  echo "Remaining snapshots:"
  restic snapshots
  
  exit 0
else
  echo "Cleanup failed"
  exit 1
fi