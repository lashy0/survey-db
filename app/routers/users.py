from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user
from app.core.database import get_db
from app.core.security import verify_password, get_password_hash
from app.models import User, Survey, SurveyResponse, Country
from app.schemas import UserProfileUpdate

router = APIRouter(prefix="/users", tags=["users"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/me", response_class=HTMLResponse)
async def read_users_me(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Profile page with stats."""
    
    # 1. Загружаем созданные опросы (сортируем по дате)
    created_surveys_query = (
        select(Survey)
        .where(Survey.author_id == current_user.user_id)
        .order_by(Survey.created_at.desc())
    )
    created_surveys = (await db.execute(created_surveys_query)).scalars().all()
    created_count = len(created_surveys)

    # 2. Загружаем пройденные опросы (уникальные по survey_id)
    # Нам нужно название опроса, поэтому делаем join или подгружаем связь
    # Важно: берем только completed_at IS NOT NULL, если считаем только завершенные
    taken_surveys_query = (
        select(SurveyResponse)
        .where(SurveyResponse.user_id == current_user.user_id)
        .options(selectinload(SurveyResponse.survey)) # Грузим сам опрос
        .order_by(SurveyResponse.started_at.desc())
    )
    taken_responses = (await db.execute(taken_surveys_query)).scalars().all()
    taken_count = len(taken_responses)

    countries = (await db.execute(select(Country).order_by(Country.name))).scalars().all()

    return templates.TemplateResponse(
        "users/profile.html", 
        {
            "request": request, 
            "user": current_user,
            "created_surveys": created_surveys,
            "created_count": created_count,
            "taken_responses": taken_responses,
            "taken_count": taken_count,
            "countries": countries
        }
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

@router.post("/update")
async def update_profile(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    form_data = await request.form()
    
    try:
        # Валидация и парсинг одной строкой
        profile_data = UserProfileUpdate(**form_data)
    except Exception as e:
        # Вернуть пользователя назад с ошибкой
        return RedirectResponse(url="/users/me?error=invalid_data", status_code=303)

    # Обновление полей (чисто и красиво)
    user.full_name = profile_data.full_name
    user.city = profile_data.city
    user.country_id = profile_data.country_id
    user.birth_date = profile_data.birth_date # Это уже date объект!
    
    db.add(user)
    await db.commit()
    return RedirectResponse(url="/users/me?msg=profile_updated", status_code=303)