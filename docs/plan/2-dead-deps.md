# Мёртвые зависимости

## Проблема

| Пакет | Где объявлен | Где используется |
|---|---|---|
| `aiodocker` | `pyproject.toml` (main deps) | Нигде — не импортируется |
| `python-multipart` | `pyproject.toml` (main deps) | Нигде — нет file upload endpoints |
| `setuptools` | `pyproject.toml` (main deps) | Build system — Poetry, не setuptools |

## Подход

1. Удалить `aiodocker` из `_core/master/pyproject.toml`
2. Удалить `python-multipart` если действительно не используется
3. Перенести `setuptools` в dev deps или удалить

## Папка

`./2-dead-deps/`
