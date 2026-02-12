#!/bin/bash

# Скрипт для запуска тестов с измерением покрытия кода

# Создаем директорию для отчетов, если её нет
mkdir -p htmlcov

# Запуск тестов с измерением покрытия
echo "Запуск тестов с измерением покрытия кода..."
pytest --cov=app --cov-report=term-missing --cov-report=html

# Проверяем успешность выполнения тестов
if [ $? -eq 0 ]; then
    echo "Тесты успешно выполнены!"
    
    # Открываем HTML отчет о покрытии (если доступен xdg-open)
    if command -v xdg-open &> /dev/null; then
        echo "Открытие HTML отчета о покрытии кода..."
        xdg-open htmlcov/index.html
    else
        echo "HTML отчет сохранен в htmlcov/index.html"
        echo "Откройте файл в браузере для просмотра отчета о покрытии кода"
    fi
else
    echo "Ошибка при выполнении тестов!"
    exit 1
fi