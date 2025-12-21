from typing import Optional
from pathlib import Path
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_optional_user, get_current_user
from app.models import User, SurveyStatus
from app.services.survey import SurveyService, User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def get_survey_service(db: AsyncSession = Depends(get_db)) -> SurveyService:
    return SurveyService(db)

@router.get("/", response_class=HTMLResponse)
async def read_root(
    request: Request, 
    user: Optional[User] = Depends(get_optional_user),
    service: SurveyService = Depends(get_survey_service)
) -> HTMLResponse:
    # Получаем все публичные опросы
    all_surveys = await service.get_public_surveys()
    
    # Получаем рекомендации (если юзер есть)
    recommendations = []
    rec_ids = set()
    
    if user:
        recommendations = await service.get_recommendations(user.user_id)
        rec_ids = {s.survey_id for s in recommendations}

    # РАЗДЕЛЯЕМ ОПРОСЫ НА СПИСКИ
    # Активные (исключая те, что уже в рекомендациях)
    active_surveys = [
        s for s in all_surveys 
        if s.status == SurveyStatus.active and s.survey_id not in rec_ids
    ]
    
    # Завершенные (архив) - их в рекомендациях быть не должно, но на всякий случай фильтруем
    completed_surveys = [
        s for s in all_surveys 
        if s.status in [SurveyStatus.completed, SurveyStatus.archived]
    ]

    return templates.TemplateResponse(
        request=request,
        name="index.html", 
        context={
            "active_surveys": active_surveys,
            "completed_surveys": completed_surveys,
            "recommendations": recommendations,
            "user": user
        }
    )

@router.get("/surveys/{survey_id}", response_class=HTMLResponse)
async def take_survey_page(
    survey_id: int,
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
    service: SurveyService = Depends(get_survey_service)
):
    survey, user_response, existing_answers = await service.get_survey_details(survey_id, user)
    
    if not survey:
        raise HTTPException(status_code=404, detail="Опрос не найден")

    is_readonly = survey.status in [SurveyStatus.completed, SurveyStatus.archived]
    
    return templates.TemplateResponse(
        request=request,
        name="survey_detail.html",
        context={
            "survey": survey,
            "user": user,
            "existing_response": user_response,
            "existing_answers": existing_answers,
            "is_readonly": is_readonly
        }
    )

@router.post("/surveys/{survey_id}/submit")
async def submit_survey(
    survey_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    service: SurveyService = Depends(get_survey_service)
):
    form_data = await request.form()
    
    # Вся сложная логика валидации и сохранения теперь в сервисе
    await service.process_survey_submission(
        user=user, 
        survey_id=survey_id, 
        form_data=form_data, 
        client_host=request.client.host
    )
    
    return RedirectResponse(
        url=f"/surveys/{survey_id}?msg=saved", 
        status_code=303
    )

@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = Path("app") / "static" / "favicon.ico"
    if not favicon_path.exists():
        return Response(status_code=404)
        
    return FileResponse(favicon_path)