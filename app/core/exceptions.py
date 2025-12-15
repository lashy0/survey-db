from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

# Инициализируем шаблоны здесь или импортируем из конфига
templates = Jinja2Templates(directory="app/templates")

async def not_found_handler(request: Request, exc: StarletteHTTPException):
    """Обработчик ошибки 404"""
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "status_code": 404,
            "title": "Страница не найдена",
            "description": "К сожалению, запрашиваемая вами страница не существует."
        },
        status_code=404
    )

async def forbidden_handler(request: Request, exc: StarletteHTTPException):
    """Обработчик ошибки 403"""
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "status_code": 403,
            "title": "Доступ запрещен",
            "description": "У вас нет прав для просмотра этой страницы."
        },
        status_code=403
    )

async def unauthorized_handler(request: Request, exc: StarletteHTTPException):
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "status_code": 401,
            "title": "Требуется авторизация",
            "description": "Пожалуйста, войдите в систему, чтобы получить доступ к этой странице."
        },
        status_code=401
    )

async def server_error_handler(request: Request, exc: Exception):
    """Обработчик ошибки 500"""
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "status_code": 500,
            "title": "Ошибка сервера",
            "description": "Мы уже работаем над исправлением."
        },
        status_code=500
    )