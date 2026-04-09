# Руководство по разработке

Это руководство предназначено для разработчиков, которые хотят внести вклад в проект или развернуть его локально для разработки.

## Структура проекта

```
apps/_core/master/
├── app/                    # Основной код приложения
│   ├── api/               # API endpoints
│   ├── core/              # Основные компоненты (база данных, события, безопасность)
│   ├── models/            # Модели данных
│   ├── services/          # Бизнес-логика
│   ├── ui/                # Пользовательский интерфейс (NiceGUI)
│   ├── config.py          # Конфигурация приложения
│   └── main.py             # Точка входа в приложение
├── tests/                 # Тесты
│   ├── unit/              # Модульные тесты
│   └── integration/       # Интеграционные тесты
├── test-fixtures/         # Фикстуры для тестов
├── docs/                  # Документация
├── docker-compose.yml     # Основная конфигурация Docker Compose
├── docker-compose.dev.yml # Конфигурация Docker Compose для разработки
├── docker-compose.test.yml # Конфигурация для тестов в контейнере
├── Dockerfile             # Dockerfile для сборки образа
├── Makefile               # Makefile с командами для разработки
├── pyproject.toml          # Конфигурация Poetry и скрипты
├── pytest.ini             # Конфигурация pytest
└── README.md             # Основная документация
```

## Работа с виртуальным окружением

### Установка Poetry

Для управления зависимостями используется Poetry. Установите его следуя официальной документации:
https://python-poetry.org/docs/#installation

### Создание виртуального окружения

После установки Poetry, перейдите в директорию проекта и установите зависимости:

```bash
cd apps/_core/master
poetry install
```

Для установки зависимостей разработки:
```bash
poetry install --with dev
```

### Активация виртуального окружения

Для активации виртуального окружения выполните:
```bash
poetry shell
```

Или запускайте команды через Poetry:
```bash
poetry run python your_script.py
```

## Запуск тестов и измерение покрытия

### Запуск всех тестов

```bash
poetry run test
```
или
```bash
poetry run pytest
```

### Запуск тестов с измерением покрытия

```bash
poetry run test-cov
```
или
```bash
poetry run pytest --cov=app
```

### Запуск тестов с генерацией HTML отчета

```bash
poetry run pytest --cov=app --cov-report=html
```

HTML отчет будет доступен в директории `htmlcov/`.

### Запуск отдельных тестов

Для запуска конкретного теста:
```bash
poetry run pytest tests/unit/test_example.py
```

Для запуска тестов в определенной директории:
```bash
poetry run pytest tests/unit/
```

## Работа с базой данных

### Локальная база данных SQLite

По умолчанию приложение использует SQLite базу данных, которая хранится в файле `master.db` в корне проекта.

### Миграции базы данных

Миграции базы данных управляются SQLAlchemy. При запуске приложения модели автоматически синхронизируются с базой данных.

Для сброса базы данных просто удалите файл `master.db`:
```bash
rm master.db
```

## Добавление новых зависимостей

### Добавление новых зависимостей

Для добавления новой зависимости выполните:
```bash
poetry add package-name
```

Для добавления зависимости разработки:
```bash
poetry add --group dev package-name
```

### Обновление зависимостей

Для обновления всех зависимостей:
```bash
poetry update
```

Для обновления конкретной зависимости:
```bash
poetry update package-name
```

### Экспорт зависимостей в requirements.txt

Для экспорта зависимостей в формате requirements.txt:
```bash
poetry export -o requirements.txt -f requirements.txt --without-hashes
```

## Работа с Docker

### Сборка образа

Для сборки Docker-образа приложения:
```bash
docker build -t apps-core-master .
```

Для сборки образа для разработки:
```bash
docker build --build-arg BUILD_ENV=dev -t apps-core-master:dev .
```

### Запуск с помощью Docker Compose

Для запуска приложения в продакшн режиме:
```bash
docker-compose up -d
```

Для запуска в режиме разработки:
```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### Остановка контейнеров

```bash
docker-compose down
```

## Работа с Makefile

В проекте используется Makefile для упрощения выполнения часто используемых команд:

```bash
make test      # Запуск тестов
make test-cov  # Запуск тестов с измерением покрытия
make test-html # Запуск тестов и открытие HTML отчета
```

## Работа с API

### Локальный доступ к API

После запуска приложения API будет доступен по адресу:
http://localhost:8000

### Документация API

Документация API доступна по адресу:
http://localhost:8000/docs

### Альтернативная документация API (ReDoc)

Альтернативная документация API доступна по адресу:
http://localhost:8000/redoc

## Работа с пользовательским интерфейсом

### Доступ к веб-интерфейсу

Пользовательский интерфейс доступен по адресу:
http://localhost:8000/ui

## Отладка

### Включение режима отладки

Для включения режима отладки установите переменную окружения:
```bash
DEBUG=true
```

### Логирование

Логи приложения доступны в консоли при запуске в режиме разработки.