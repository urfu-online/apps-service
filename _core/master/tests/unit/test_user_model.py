"""Тесты для модели пользователя."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.user import User, Role, user_roles
from app.core.database import Base


@pytest.fixture
def db_session():
    """Фикстура для создания тестовой базы данных."""
    # Создаем in-memory SQLite базу для тестов
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    yield session
    
    session.close()


@pytest.fixture
def sample_role():
    """Фикстура для создания тестовой роли."""
    return Role(
        id=1,
        name="admin",
        description="Administrator role",
        permissions="read,write,delete"
    )


@pytest.fixture
def sample_user(sample_role):
    """Фикстура для создания тестового пользователя."""
    user = User(
        id=1,
        username="testuser",
        email="testuser@example.com",
        hashed_password="hashed_password",
        is_active=True,
        is_superuser=False
    )
    user.roles = [sample_role]
    return user


def test_user_creation(db_session, sample_user):
    """Тест создания пользователя."""
    # Добавляем пользователя в базу
    db_session.add(sample_user)
    db_session.commit()
    db_session.refresh(sample_user)
    
    # Проверяем, что пользователь был сохранен
    assert sample_user.id is not None
    assert sample_user.username == "testuser"
    assert sample_user.email == "testuser@example.com"
    assert sample_user.hashed_password == "hashed_password"
    assert sample_user.is_active is True
    assert sample_user.is_superuser is False


def test_user_has_role_success(sample_user, sample_role):
    """Тест успешной проверки наличия роли у пользователя."""
    result = sample_user.has_role("admin")
    assert result is True


def test_user_has_role_failure(sample_user):
    """Тест неудачной проверки наличия роли у пользователя."""
    result = sample_user.has_role("nonexistent")
    assert result is False


def test_user_get_permissions(sample_user):
    """Тест получения разрешений пользователя."""
    permissions = sample_user.get_permissions()
    
    assert permissions is not None
    assert isinstance(permissions, list)
    assert "read" in permissions
    assert "write" in permissions
    assert "delete" in permissions


def test_user_get_permissions_empty_role(sample_user):
    """Тест получения разрешений пользователя с пустой ролью."""
    # Создаем роль без разрешений
    empty_role = Role(
        id=2,
        name="user",
        description="Regular user",
        permissions=None
    )
    
    # Устанавливаем пользователю пустую роль
    sample_user.roles = [empty_role]
    
    # Получаем разрешения
    permissions = sample_user.get_permissions()
    
    # Проверяем результат
    assert permissions is not None
    assert isinstance(permissions, list)
    assert len(permissions) == 0


def test_user_get_permissions_multiple_roles(sample_user):
    """Тест получения разрешений пользователя с несколькими ролями."""
    # Создаем вторую роль
    second_role = Role(
        id=2,
        name="editor",
        description="Editor role",
        permissions="read,write"
    )
    
    # Добавляем вторую роль пользователю
    sample_user.roles.append(second_role)
    
    # Получаем разрешения
    permissions = sample_user.get_permissions()
    
    # Проверяем результат (дубликаты должны быть удалены)
    assert permissions is not None
    assert isinstance(permissions, list)
    assert "read" in permissions
    assert "write" in permissions
    assert "delete" in permissions
    # Проверяем, что нет дубликатов
    assert len(permissions) == 3


def test_role_creation(db_session):
    """Тест создания роли."""
    # Создаем роль
    role = Role(
        id=1,
        name="admin",
        description="Administrator role",
        permissions="read,write,delete"
    )
    
    # Добавляем роль в базу
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    
    # Проверяем атрибуты
    assert role.id is not None
    assert role.name == "admin"
    assert role.description == "Administrator role"
    assert role.permissions == "read,write,delete"


def test_user_role_relationship(db_session, sample_user, sample_role):
    """Тест связи между пользователем и ролями."""
    # Добавляем роль и пользователя в базу
    db_session.add(sample_role)
    db_session.add(sample_user)
    db_session.commit()
    
    # Проверяем связь
    assert len(sample_user.roles) == 1
    assert sample_user.roles[0].name == "admin"
    assert sample_role.users[0].username == "testuser"


def test_user_serialization(sample_user):
    """Тест сериализации пользователя."""
    # Проверяем, что у пользователя есть методы для сериализации
    # (в SQLAlchemy модели обычно не имеют явных методов сериализации,
    # но мы можем проверить доступ к атрибутам)
    assert hasattr(sample_user, 'id')
    assert hasattr(sample_user, 'username')
    assert hasattr(sample_user, 'email')
    assert hasattr(sample_user, 'is_active')
    assert hasattr(sample_user, 'is_superuser')
    assert hasattr(sample_user, 'roles')


def test_role_serialization(sample_role):
    """Тест сериализации роли."""
    # Проверяем, что у роли есть атрибуты
    assert hasattr(sample_role, 'id')
    assert hasattr(sample_role, 'name')
    assert hasattr(sample_role, 'description')
    assert hasattr(sample_role, 'permissions')
    assert hasattr(sample_role, 'users')