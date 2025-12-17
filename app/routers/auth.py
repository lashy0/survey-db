from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
import pwdlib.exceptions 

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, get_password_hash, verify_password, create_refresh_token
from app.models import User
from app.core.deps import check_csrf

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")

def create_login_response(user_email: str) -> RedirectResponse:
    """Создает ответ с ДВУМЯ токенами"""
    
    # 1. Access Token (короткий)
    access_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user_email}, expires_delta=access_expires
    )
    
    # 2. Refresh Token (длинный)
    refresh_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_token = create_refresh_token(
        data={"sub": user_email}, expires_delta=refresh_expires
    )
    
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    
    # Кука 1: Access
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=int(access_expires.total_seconds()),
        samesite="lax",
        secure=False 
    )
    
    # Кука 2: Refresh (Путь можно ограничить, но для Middleware проще оставить глобальным)
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=int(refresh_expires.total_seconds()),
        samesite="lax",
        secure=False 
    )
    
    return response


# --- Эндпоинты ---

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="auth/register.html"
    )

@router.post("/register")
async def register_user(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    # Проверка на существование
    existing_user = await db.execute(select(User).where(User.email == email))
    if existing_user.scalar_one_or_none():
        return templates.TemplateResponse(
            request=request,
            name="auth/register.html", 
            context={
                "error": "Email уже зарегистрирован"
            },
            status_code=400
        )

    # Создание пользователя
    new_user = User(
        email=email,
        password_hash=get_password_hash(password),
        first_name=full_name, # Используем full_name как first_name пока что
        birth_date=None, 
        country_id=1 
    )
    
    db.add(new_user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return templates.TemplateResponse(
            request=request,
            name="auth/register.html", 
            context={
                "error": "Ошибка базы данных"
            },
            status_code=500
        )

    # Автоматический вход после регистрации
    return create_login_response(email)

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html"
    )

@router.post("/login", dependencies=[Depends(check_csrf)])
async def login_user(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    # Поиск пользователя
    user_query = await db.execute(select(User).where(User.email == email))
    user = user_query.scalar_one_or_none()

    # Проверка пароля
    is_valid = False
    if user:
        try:
            is_valid = verify_password(password, user.password_hash)
        except (pwdlib.exceptions.UnknownHashError, ValueError):
            # Если хеш в базе битый или старый формат, считаем невалидным
            is_valid = False

    if not user or not is_valid:
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html", 
            context={
                "error": "Неверный email или пароль"
            },
            status_code=401 
        )

    # Успешный вход
    return create_login_response(user.email)

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response