from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.database import async_session_maker
from app.core.deps import get_optional_user


# Инициализируем шаблоны здесь или импортируем из конфига
templates = Jinja2Templates(directory="app/templates")

async def get_user_context(request: Request):
    """
    Вспомогательная функция: пытается получить пользователя для контекста шаблона,
    так как Dependency Injection не работает в обработчиках исключений.
    """
    try:
        async with async_session_maker() as session:
            return await get_optional_user(request, session)
    except:
        return None

async def not_found_handler(request: Request, exc: StarletteHTTPException):
    """Обработчик ошибки 404"""
    user = await get_user_context(request)
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "status_code": 404,
            "title": "Страница не найдена",
            "description": "К сожалению, запрашиваемая вами страница не существует.",
            "user": user
        },
        status_code=404
    )

async def forbidden_handler(request: Request, exc: StarletteHTTPException):
    """Обработчик ошибки 403"""
    user = await get_user_context(request)
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "status_code": 403,
            "title": "Доступ запрещен",
            "description": "У вас нет прав для просмотра этой страницы.",
            "user": user
        },
        status_code=403
    )

async def unauthorized_handler(request: Request, exc: StarletteHTTPException):
    user = await get_user_context(request)
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "status_code": 401,
            "title": "Требуется авторизация",
            "description": "Пожалуйста, войдите в систему, чтобы получить доступ к этой странице.",
            "user": user
        },
        status_code=401
    )

async def server_error_handler(request: Request, exc: Exception):
    """Обработчик ошибки 500"""
    user = await get_user_context(request)
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "status_code": 500,
            "title": "Ошибка сервера",
            "description": "Мы уже работаем над исправлением.",
            "user": user
        },
        status_code=500
    )