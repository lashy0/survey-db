from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Request, status
import jwt # PyJWT
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import secrets

from app.core.config import settings
from app.core.database import get_db
from app.models import User

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    token = request.cookies.get("access_token")
    
    exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )

    if not token:
        raise exception

    try:
        # PyJWT decode
        payload = jwt.decode(
            token, 
            settings.SECRET_KEY, 
            algorithms=[settings.ALGORITHM]
        )
        user_email: str = payload.get("sub")
        if user_email is None:
            raise exception
            
    except jwt.ExpiredSignatureError:
        # Токен просрочен
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except jwt.PyJWTError: # Базовое исключение PyJWT
        raise exception

    # Далее поиск в БД без изменений...
    query = (
        select(User)
        .where(User.email == user_email)
        .options(selectinload(User.country)) 
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if user is None:
        raise exception

    return user


async def get_optional_user(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Возвращает пользователя, если он залогинен, иначе None.
    Не вызывает HTTPException.
    """
    try:
        return await get_current_user(request, db)
    except HTTPException:
        return None


async def check_csrf(request: Request):
    # Проверяем только небезопасные методы
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        csrf_token = request.cookies.get("csrf_token")
        # Получаем данные формы. 
        # В зависимостях FastAPI и Starlette request.form() кэшируется, 
        # поэтому здесь вызов безопасен, если он происходит в контексте роутера.
        form = await request.form()
        submitted_token = form.get("csrf_token")
        
        # Заголовок (для HTMX)
        if not submitted_token:
            submitted_token = request.headers.get("X-CSRF-Token")
            
        if not csrf_token or not submitted_token or not secrets.compare_digest(submitted_token, csrf_token):
            raise HTTPException(status_code=403, detail="CSRF Token Mismatch")