"""Интеграционные тесты API для endpoints пользователей."""
from __future__ import annotations

import bcrypt
import httpx
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import AsyncMock, patch


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


@pytest.mark.asyncio
async def test_services_api_with_routing_types(client, temp_services_dir):
    """Тестирование API /api/services с разными типами сервисов."""
    from app.services.discovery import ServiceDiscovery
    from app.main import app
    from app.core.security import get_current_user
    from app.models.user import User
    
    # Переопределяем зависимость get_current_user
    async def mock_get_current_user():
        return User(username="test", is_superuser=True, id=1)
    
    app.dependency_overrides[get_current_user] = mock_get_current_user
    
    try:
        # Мокаем ServiceDiscovery в состоянии приложения
        with patch.object(ServiceDiscovery, "_get_docker_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = "unknown"
            with patch.object(ServiceDiscovery, "_setup_watcher"):
                discovery = ServiceDiscovery(str(temp_services_dir))
                services = await discovery.scan_all()
                
                # Устанавливаем discovery в состояние приложения
                app.state.discovery = discovery
                
                # Проверяем, что discovery установлен
                assert app.state.discovery is not None
                assert len(app.state.discovery.services) == 9
                
                # Проверяем, что маршрут существует
                from fastapi.routing import APIRoute
                all_routes = [route.path for route in app.routes if isinstance(route, APIRoute)]
                print("Available API routes:", all_routes)
                routes = [route for route in app.routes if isinstance(route, APIRoute) and (route.path == "/api/services" or route.path == "/api/services/")]
                assert len(routes) > 0, f"Route /api/services not found in app.routes. Available routes: {all_routes}"
                
                # Делаем запрос к /api/services (со слэшем, как в маршруте)
                response = await client.get("/api/services/")
                assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text}"
                data = response.json()
                
                # Проверяем, что все сервисы присутствуют в ответе
                service_names = {s["name"] for s in data}
                expected_names = {
                    "test-web-app", "test-auto-sub", "test-domain",
                    "test-subfolder", "test-multi-container", "test-multi-route",
                    "test-api", "test-health-only", "test-port-internal"
                }
                assert service_names == expected_names
                
                # Проверяем, что у каждого сервиса есть правильные поля (согласно ServiceResponse)
                for service in data:
                    assert "name" in service
                    assert "display_name" in service
                    assert "version" in service
                    assert "visibility" in service
                    assert "status" in service
                    assert "type" in service
                    # Поле routing не возвращается API, поэтому не проверяем
    finally:
        # Очищаем переопределения
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_tls_validation_api(client, temp_services_dir):
    """Тестирование API /api/tls/validate для auto_subdomain."""
    from app.services.discovery import ServiceDiscovery
    from app.main import app
    
    with patch.object(ServiceDiscovery, "_get_docker_status", new_callable=AsyncMock) as mock_status:
        mock_status.return_value = "unknown"
        with patch.object(ServiceDiscovery, "_setup_watcher"):
            discovery = ServiceDiscovery(str(temp_services_dir))
            await discovery.scan_all()
            
            app.state.discovery = discovery
            
            # Проверяем, что маршрут существует
            from fastapi.routing import APIRoute
            all_routes = [route.path for route in app.routes if isinstance(route, APIRoute)]
            print("Available API routes:", all_routes)
            routes = [route for route in app.routes if isinstance(route, APIRoute) and route.path == "/api/tls/validate"]
            assert len(routes) > 0, f"Route /api/tls/validate not found in app.routes. Available routes: {all_routes}"
            
            # Валидация домена для auto_subdomain сервиса
            response = await client.get("/api/tls/validate", params={"domain": "test-auto-sub.apps.example.com"})
            assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text}"
            data = response.json()
            assert data["status"] == "ok"
            assert data["service"] == "test-auto-sub"
            
            # Валидация домена для domain сервиса
            response = await client.get("/api/tls/validate", params={"domain": "test-domain.example.com"})
            assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text}"
            data = response.json()
            assert data["status"] == "ok"
            assert data["service"] == "test-domain"
            
            # Неизвестный домен должен вернуть 403
            response = await client.get("/api/tls/validate", params={"domain": "unknown.example.com"})
            assert response.status_code == 403, f"Expected 403, got {response.status_code}. Response: {response.text}"
            data = response.json()
            assert "detail" in data
