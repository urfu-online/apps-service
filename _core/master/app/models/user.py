from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Table
from sqlalchemy.orm import relationship
from typing import List, Optional
from app.core.database import Base

# Ассоциативная таблица для связи пользователей и ролей
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
)


class User(Base):
    """Модель пользователя"""
    
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    
    # Связь с ролями
    roles = relationship("Role", secondary=user_roles, back_populates="users")
    
    def has_role(self, role_name: str) -> bool:
        """Проверка наличия роли у пользователя"""
        return any(role.name == role_name for role in self.roles)
    
    def get_permissions(self) -> List[str]:
        """Получение всех разрешений пользователя"""
        permissions = set()
        for role in self.roles:
            permissions.update(role.permissions.split(",") if role.permissions else [])
        return list(permissions)


class Role(Base):
    """Модель роли"""
    
    __tablename__ = "roles"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String)
    permissions = Column(String)  # Разрешения через запятую
    
    # Связь с пользователями
    users = relationship("User", secondary=user_roles, back_populates="roles")