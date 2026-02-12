#!/bin/bash

# Функция для отображения справки
usage() {
    echo "Использование: $0 [--build]"
    echo "  --build    Пересобрать образы перед запуском"
    echo "  без флагов  Простой рестарт без пересборки"
    exit 1
}

# Переменная для хранения флага --build
BUILD_FLAG=""

# Обработка аргументов командной строки
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --build)
            BUILD_FLAG="--build"
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Неизвестный параметр: $1"
            usage
            ;;
    esac
    shift
done

# Рестарт master-сервисов
echo "Останавливаю master-сервис..."
docker compose -f _core/master/docker-compose.yml down

echo "Запускаю master-сервис..."
docker compose -f _core/master/docker-compose.yml up -d $BUILD_FLAG

# Рестарт Caddy
echo "Останавливаю Caddy..."
docker compose -f _core/caddy/docker-compose.yml down

echo "Запускаю Caddy..."
docker compose -f _core/caddy/docker-compose.yml up -d $BUILD_FLAG

echo "✅ Обновление завершено."
