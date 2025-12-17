from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_optional_user, get_current_user
from app.models import User, SurveyStatus
from app.services.survey import SurveyService # Импорт

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
    surveys = await service.get_active_surveys()
    return templates.TemplateResponse(
        request=request,
        name="index.html", 
        context={
            "surveys": surveys,
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
    user_id = user.user_id if user else None
    survey, user_response, existing_answers = await service.get_survey_details(survey_id, user_id)
    
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