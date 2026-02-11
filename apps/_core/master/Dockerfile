# Используем официальный образ Python
FROM python:3.12-slim

# Установка переменных окружения
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV POETRY_NO_INTERACTION=1
ENV POETRY_VIRTUALENVS_CREATE=false
ENV POETRY_CACHE_DIR=/tmp/poetry_cache

# Установка рабочей директории
WORKDIR /app

# Установка системных зависимостей (как root)
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Установка Poetry (как root, в /usr/local)
RUN pip install --upgrade pip && pip install poetry

# Копирование файлов конфигурации
COPY pyproject.toml poetry.lock README.md ./
COPY app/ ./app/

# Установка зависимостей напрямую в системный Python (без virtualenv)
RUN poetry install --only=main --no-root && \
    rm -rf $POETRY_CACHE_DIR

# Создание пользователя и смена владельца файлов
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app

# Переключение на пользователя app
USER app

# Открытие портов и запуск
EXPOSE 8000
ENV APP_ENV=prod
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "debug"]
