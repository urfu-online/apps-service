# Makefile для запуска тестов и других команд

# Команда по умолчанию
.PHONY: help test test-cov test-html dev start

help:
	@echo "Доступные команды:"
	@echo "  make dev        - Запуск приложения в режиме разработки"
	@echo "  make start      - Запуск приложения в продакшн режиме"
	@echo "  make test       - Запуск тестов"
	@echo "  make test-cov   - Запуск тестов с измерением покрытия"
	@echo "  make test-html - Запуск тестов и открытие HTML отчета"

# Запуск приложения в режиме разработки
dev:
	@poetry run dev

# Запуск приложения в продакшн режиме
start:
	@poetry run start

# Запуск тестов
test:
	@pytest

# Запуск тестов с измерением покрытия
test-cov:
	@pytest --cov=app --cov-report=term-missing

# Запуск тестов и открытие HTML отчета
test-html:
	@pytest --cov=app --cov-report=term-missing --cov-report=html
	@echo "HTML отчет о покрытии кода сохранен в htmlcov/index.html"
	if command -v xdg-open &> /dev/null; then \
		xdg-open htmlcov/index.html; \
	else \
		echo "Откройте htmlcov/index.html в браузере для просмотра отчета"; \
	fi

# Запуск тестов с генерацией бейджа покрытия
test-badge:
	@pytest --cov=app --cov-report=term-missing --cov-report=html
	@coverage-badge -o htmlcov/coverage.svg -f
	@echo "Бейдж покрытия кода сохранен в htmlcov/coverage.svg"