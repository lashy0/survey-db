from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.database import get_db
from app.core.security import verify_password, get_password_hash
from app.models import User

router = APIRouter(prefix="/users", tags=["users"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/me", response_class=HTMLResponse)
async def read_users_me(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Profile page. Only accessible if logged in."""
    return templates.TemplateResponse(
        "users/profile.html", 
        {"request": request, "user": current_user}
    )

# --- Смена пароля ---

@router.get("/password", response_class=HTMLResponse)
async def change_password_page(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Form for changing password."""
    return templates.TemplateResponse(
        "users/change_password.html",
        {"request": request, "user": current_user}
    )

@router.post("/password")
async def change_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Process password change."""
    # 1. Проверка старого пароля
    if not verify_password(old_password, current_user.password_hash):
        return templates.TemplateResponse(
            "users/change_password.html",
            {
                "request": request, 
                "user": current_user, 
                "error": "Старый пароль введен неверно"
            }
        )

    # 2. Проверка совпадения новых паролей
    if new_password != confirm_password:
        return templates.TemplateResponse(
            "users/change_password.html",
            {
                "request": request, 
                "user": current_user, 
                "error": "Новые пароли не совпадают"
            }
        )
    
    # 3. Обновление в БД
    current_user.password_hash = get_password_hash(new_password)
    db.add(current_user)
    await db.commit()

    # 4. Редирект в профиль с флагом успеха
    return RedirectResponse(url="/users/me?msg=password_updated", status_code=303)