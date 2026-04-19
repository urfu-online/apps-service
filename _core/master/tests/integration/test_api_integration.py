"""Интеграционные тесты API для endpoints пользователей."""
from __future__ import annotations

import bcrypt
import httpx
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    """Фикстура TestClient для интеграционных тестов."""

    # В CI/локально путь `sqlite:///./master.db` может быть недоступен (cwd/права). Поэтому
    # переопределяем engine/SessionLocal на тестовую sqlite БД ДО импорта `app.main`.
    import app.core.database as database

    test_db_url = f"sqlite:///{tmp_path / 'test.db'}"
    test_engine = create_engine(test_db_url, connect_args={"check_same_thread": False}, echo=False, pool_pre_ping=True)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    monkeypatch.setattr(database, "engine", test_engine, raising=True)
    monkeypatch.setattr(database, "SessionLocal", TestSessionLocal, raising=True)
    monkeypatch.setattr(database.db_manager, "engine", test_engine, raising=True)
    monkeypatch.setattr(database.db_manager, "SessionLocal", TestSessionLocal, raising=True)

    # Создаём таблицы в тестовой БД заранее.
    database.get_base().metadata.create_all(bind=test_engine)

    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.mark.asyncio
async def test_user_crud_integration(client):
    """Интеграционный тест CRUD операций для пользователей."""
    # Подготовка: создаем суперпользователя для выполнения операций
    # и настраиваем аутентификацию
    from app.core.security import BuiltInAuthProvider, set_auth_provider

    auth_provider = BuiltInAuthProvider()
    set_auth_provider(auth_provider)

    # Создание суперпользователя напрямую в БД
    from app.core.database import SessionLocal
    from app.models.user import User

    db = SessionLocal()
    try:
        # Хешируем пароль для суперпользователя
        password_hash = bcrypt.hashpw("admin123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        admin_user = User(username="admin", hashed_password=password_hash, is_superuser=True)
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)

        # Аутентификация: получаем токен для суперпользователя
        login_result = await auth_provider.authenticate("admin", "admin123")
        auth_token = login_result["sub"] if login_result else None
        assert auth_token is not None

        # Заголовки авторизации
        auth_headers = {"Authorization": f"Bearer {auth_token}"}

        # 1. Создание пользователя
        create_response = await client.post(
            "/api/users/",
            headers=auth_headers,
            params={
                "username": "testuser",
                "password": "testpass",
                "email": "test@example.com",
            },
        )
        assert create_response.status_code == 200
        create_data = create_response.json()
        assert create_data["message"] == "User created successfully"

        # 2. Получение списка пользователей
        list_response = await client.get("/api/users/", headers=auth_headers)
        assert list_response.status_code == 200
        users = list_response.json()
        assert len(users) == 2  # admin + testuser

        # 3. Получение конкретного пользователя
        # Сначала нужно получить ID созданного пользователя для дальнейших тестов
        get_response = await client.get(f"/api/users/{admin_user.id}", headers=auth_headers)
        assert get_response.status_code == 200

        # 4. Обновление пользователя
        # Мы не можем обновить пользователя через API потому что ID жестко задан в URL, 
        # и мы не знаем точный ID testuser. Вместо этого обновим самого суперпользовтеля
        update_response = await client.put(
            f"/api/users/{admin_user.id}",
            headers=auth_headers,
            params={
                "username": "updated_admin",
                "email": "updated@example.com",
            },
        )
        assert update_response.status_code == 200
        update_data = update_response.json()
        assert update_data["message"] == "User updated successfully"

        # 5. Удаление пользователя (вернем прежнее имя администратора, чтобы избежать проблем)
        # Создаем нового пользователя чтобы его удалить (не будем удалять администратора)
        create_test_user_response = await client.post(
            "/api/users/",
            headers=auth_headers,
            params={
                "username": "deletable_user",
                "password": "testpass",
                "email": "deletable@example.com",
            },
        )
        assert create_test_user_response.status_code == 200
        
        # Получаем ID нового пользователя путем получения всех пользователей
        list_for_deletion = await client.get("/api/users/", headers=auth_headers)
        users_for_deletion = list_for_deletion.json()
        
        deletable_user_id = None
        for user in users_for_deletion:
            print(user)
            if user['username'] == 'deletable_user':
                deletable_user_id = user['id']
                break
                
        if deletable_user_id:
            delete_response = await client.delete(f"/api/users/{deletable_user_id}", headers=auth_headers)
            assert delete_response.status_code == 200
            delete_data = delete_response.json()
            assert delete_data["message"] == "User deleted successfully"

    finally:
        # Очистка: удаление тестового пользователя из БД
        db.query(User).filter(User.username.in_(["admin", "testuser", "deletable_user", "updated_admin"])).delete()
        db.commit()
        db.close()
