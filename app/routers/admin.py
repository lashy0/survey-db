from typing import Optional, Union
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, case, text, extract
# Убрал distinct из импорта, будем использовать метод .distinct()
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User, Survey, SurveyResponse, Tag, survey_tags, UserRole

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/analytics", response_class=HTMLResponse)
async def analytics_dashboard(
    request: Request,
    survey_id: Union[int, str, None] = None, 
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
) -> HTMLResponse:
    if survey_id is not None:
        try:
            survey_id = int(survey_id)
        except ValueError:
            survey_id = None
    
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Доступ запрещен")

    # --- 0. ЗАГРУЗКА СПИСКА ОПРОСОВ (для фильтра) ---
    all_surveys = (await db.execute(select(Survey).order_by(Survey.title))).scalars().all()

    # --- KPI и ГРАФИКИ (Оставляем как есть) ---
    total_users = await db.scalar(select(func.count(User.user_id))) or 0
    total_surveys = await db.scalar(select(func.count(Survey.survey_id))) or 0
    total_responses = await db.scalar(select(func.count(SurveyResponse.response_id))) or 0
    
    cnt_users = total_users
    # Используем метод .distinct() у колонки - это самый надежный способ в ORM
    cnt_started = await db.scalar(select(func.count(SurveyResponse.user_id.distinct()))) or 0
    
    cnt_completed = await db.scalar(
        select(func.count(SurveyResponse.user_id.distinct()))
        .where(SurveyResponse.completed_at.is_not(None))
    ) or 0
    
    funnel_data = {
        "labels": ["Регистрация", "Начали опрос", "Завершили опрос"],
        "counts": [int(cnt_users), int(cnt_started), int(cnt_completed)]
    }

    activity_query = (
        select(
            func.date(SurveyResponse.started_at).label("date"),
            func.count(SurveyResponse.response_id).label("cnt")
        )
        .group_by(func.date(SurveyResponse.started_at))
        .order_by(func.date(SurveyResponse.started_at))
    )
    activity_res = (await db.execute(activity_query)).all()
    time_series_data = {
        "dates": [str(row.date) for row in activity_res],
        "counts": [int(row.cnt) for row in activity_res]
    }

    tags_query = (
        select(Tag.name, func.count(SurveyResponse.response_id).label("popularity"))
        .select_from(SurveyResponse)
        .join(Survey, SurveyResponse.survey_id == Survey.survey_id)
        .join(survey_tags, Survey.survey_id == survey_tags.c.survey_id)
        .join(Tag, survey_tags.c.tag_id == Tag.tag_id)
        .where(SurveyResponse.completed_at.is_not(None))
        .group_by(Tag.name)
        .order_by(desc("popularity"))
        .limit(7)
    )
    tags_res = (await db.execute(tags_query)).all()
    tags_data = {
        "labels": [str(row.name) for row in tags_res],
        "counts": [int(row.popularity) for row in tags_res]
    }

    # --- 4. ANOMALIES (С ФИЛЬТРАЦИЕЙ) ---
    stats_cte = (
        select(
            SurveyResponse.survey_id,
            func.avg(extract('epoch', SurveyResponse.duration)).label("avg_sec"),
            func.stddev(extract('epoch', SurveyResponse.duration)).label("std_sec")
        )
        .where(SurveyResponse.duration.is_not(None))
        .group_by(SurveyResponse.survey_id)
        .cte("survey_stats")
    )

    anomalies_query = (
        select(
            User.full_name,
            User.email,
            Survey.title,
            extract('epoch', SurveyResponse.duration).label("user_sec"),
            stats_cte.c.avg_sec,
            stats_cte.c.std_sec
        )
        .join(stats_cte, SurveyResponse.survey_id == stats_cte.c.survey_id)
        .join(User, SurveyResponse.user_id == User.user_id)
        .join(Survey, SurveyResponse.survey_id == Survey.survey_id)
        .where(
            extract('epoch', SurveyResponse.duration) < (stats_cte.c.avg_sec - 1.5 * func.coalesce(stats_cte.c.std_sec, 0))
        )
        .order_by("user_sec")
        # Убрали limit(10), чтобы показать всех
    )
    
    # ЕСЛИ ВЫБРАН ОПРОС — ДОБАВЛЯЕМ WHERE
    if survey_id:
        anomalies_query = anomalies_query.where(Survey.survey_id == survey_id)
    
    anomalies_res = (await db.execute(anomalies_query)).all()

    return templates.TemplateResponse(
        name="admin/analytics.html",
        context={
            "request": request,
            "user": user,
            "kpi": {
                "users": total_users,
                "surveys": total_surveys,
                "responses": total_responses
            },
            "funnel_data": funnel_data,
            "time_series_data": time_series_data,
            "tags_data": tags_data,
            "anomalies": anomalies_res,
            "all_surveys": all_surveys, # Передаем список опросов
            "selected_survey_id": survey_id # Передаем текущий выбор
        }
    )


@router.get("/analytics/anomalies", response_class=HTMLResponse)
async def get_anomalies_partial(
    request: Request,
    survey_id: Union[int, str, None] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Возвращает только HTML-фрагмент таблицы аномалий."""
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403)

    # Обработка survey_id (так же как выше)
    if survey_id == "": survey_id = None
    if survey_id is not None:
        try: survey_id = int(survey_id)
        except: survey_id = None

    # Повторяем запрос аномалий (можно вынести в отдельную функцию, чтобы не дублировать)
    stats_cte = (
        select(
            SurveyResponse.survey_id,
            func.avg(extract('epoch', SurveyResponse.duration)).label("avg_sec"),
            func.stddev(extract('epoch', SurveyResponse.duration)).label("std_sec")
        )
        .where(SurveyResponse.duration.is_not(None))
        .group_by(SurveyResponse.survey_id)
        .cte("survey_stats")
    )

    anomalies_query = (
        select(
            User.full_name,
            User.email,
            Survey.title,
            extract('epoch', SurveyResponse.duration).label("user_sec"),
            stats_cte.c.avg_sec,
            stats_cte.c.std_sec
        )
        .join(stats_cte, SurveyResponse.survey_id == stats_cte.c.survey_id)
        .join(User, SurveyResponse.user_id == User.user_id)
        .join(Survey, SurveyResponse.survey_id == Survey.survey_id)
        .where(
            extract('epoch', SurveyResponse.duration) < (stats_cte.c.avg_sec - 1.5 * func.coalesce(stats_cte.c.std_sec, 0))
        )
        .order_by("user_sec")
    )
    
    if survey_id:
        anomalies_query = anomalies_query.where(Survey.survey_id == survey_id)
    
    anomalies_res = (await db.execute(anomalies_query)).all()

    # Возвращаем только фрагмент!
    return templates.TemplateResponse(
        "admin/partials/anomalies_table.html",
        {"request": request, "anomalies": anomalies_res}
    )