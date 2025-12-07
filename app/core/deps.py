from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Request, status
import jwt # PyJWT
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    query = select(User).where(User.email == user_email)
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