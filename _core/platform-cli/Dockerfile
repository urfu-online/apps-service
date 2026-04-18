FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копирование исходного кода
COPY pyproject.toml ./
COPY apps_platform/ ./apps_platform/

# Установка platform-cli
RUN pip install --no-cache-dir .

# Создание пользователя для безопасности
RUN useradd -m -u 1000 platform && \
    chown -R platform:platform /app
USER platform

ENTRYPOINT ["platform"]
CMD ["--help"]
