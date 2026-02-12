from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.core.security import get_current_user
from app.core.security import BuiltInAuthProvider
from app.models import User, Role
from app.core.database import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/users", tags=["users"])

# Встроенный провайдер аутентификации для управления пользователями
auth_provider = BuiltInAuthProvider()


@router.get("/")
async def list_users(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Получение списка пользователей"""
    # Проверка прав доступа
    if not current_user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    # Получение списка пользователей
    users = db.query(User).all()
    return users


@router.post("/")
async def create_user(
    username: str, 
    password: str, 
    email: str = None,
    is_superuser: bool = False,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Создание нового пользователя"""
    # Проверка прав доступа
    if not current_user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    # Проверка существования пользователя
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    
    # Создание нового пользователя через провайдер
    user_info = await auth_provider.create_user(username, password, [])
    
    if not user_info:
        raise HTTPException(status_code=500, detail="Error creating user")
    
    # Обновление дополнительной информации
    user = db.query(User).filter(User.username == username).first()
    user.email = email
    user.is_superuser = is_superuser
    db.commit()
    
    return {"message": "User created successfully", "user": user_info}


@router.get("/{user_id}")
async def get_user(
    user_id: int, 
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Получение информации о пользователе"""
    # Проверка прав доступа
    if not current_user.get("is_superuser", False) and current_user.get("sub") != str(user_id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    # Получение пользователя
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user


@router.put("/{user_id}")
async def update_user(
    user_id: int,
    username: str = None,
    email: str = None,
    is_active: bool = None,
    is_superuser: bool = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Обновление информации о пользователе"""
    # Проверка прав доступа
    if not current_user.get("is_superuser", False) and current_user.get("sub") != str(user_id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    # Получение пользователя
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Обновление информации
    if username is not None:
        user.username = username
    if email is not None:
        user.email = email
    if is_active is not None:
        user.is_active = is_active
    if is_superuser is not None:
        user.is_superuser = is_superuser
    
    db.commit()
    db.refresh(user)
    
    return {"message": "User updated successfully", "user": user}


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Удаление пользователя"""
    # Проверка прав доступа
    if not current_user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    # Получение пользователя
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Удаление пользователя
    db.delete(user)
    db.commit()
    
    return {"message": "User deleted successfully"}