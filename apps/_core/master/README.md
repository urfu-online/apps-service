# Apps Core Master Service

Core master service for managing applications and services.

## Установка и настройка Poetry

Для управления зависимостями в этом проекте используется Poetry. Следуйте этим шагам для настройки окружения:

### 1. Установка Poetry

Для установки Poetry следуйте официальной документации: https://python-poetry.org/docs/#installation

Для Linux/macOS можно использовать следующую команду:

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

Убедитесь, что Poetry добавлена в PATH:

```bash
poetry --version
```

### 2. Клонирование репозитория и переход в директорию проекта:

```bash
cd apps/_core/master
```

### 3. Установка зависимостей проекта:

```bash
poetry install
```

Для разработки (включая зависимости для тестирования):

```bash
poetry install --with dev
```

## Запуск приложения

### Режим разработки

Для запуска приложения в режиме разработки с автоматической перезагрузкой при изменении кода:

```bash
poetry run dev
```

или

```bash
poetry run uvicorn app.main:app --reload
```

### Продакшн режим

Для запуска приложения в продакшн режиме:

```bash
poetry run start
```

или

```bash
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Тестирование

### Запуск тестов

Для запуска тестов выполните:

```bash
poetry run test
```

или

```bash
poetry run pytest
```

### Запуск тестов с покрытием

Для запуска тестов с анализом покрытия кода:

```bash
poetry run test-cov
```

или

```bash
poetry run pytest --cov=app
```

## Использование Docker

### Сборка образа

Для сборки Docker-образа приложения выполните:

```bash
docker build -t apps-core-master .
```

Для сборки образа для разработки:

```bash
docker build --build-arg BUILD_ENV=dev -t apps-core-master:dev .
```

### Запуск с помощью Docker

Для запуска приложения в контейнере Docker:

```bash
docker run -p 8000:8000 apps-core-master
```

### Запуск с помощью Docker Compose

Для запуска приложения с помощью Docker Compose:

```bash
docker compose up -d
```

Для запуска в режиме разработки:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```
