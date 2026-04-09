# Миграции БД (Alembic)

## Проблема

`_core/master/app/core/database.py`:

```python
Base.metadata.create_all(bind=self.engine)  # При каждом старте
```

- Нет Alembic, нет миграций
- Изменение модели → нужно дропать/пересоздавать БД вручную
- Потеря данных при любом изменении схемы

## Подход

1. `pip install alembic`
2. `alembic init alembic`
3. Настроить `alembic.ini` → `DATABASE_URL`
4. `alembic revision --autogenerate` — первая миграция
5. Заменить `create_all()` на `alembic upgrade head` в startup

## Папка

`./9-alembic-migrations/`
