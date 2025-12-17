import json
from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas import SurveyCreateForm
from app.core.utils import parse_form_data
from app.services.survey import SurveyService

router = APIRouter(prefix="/surveys", tags=["surveys"])
templates = Jinja2Templates(directory="app/templates")

# Зависимость сервиса
def get_survey_service(db: AsyncSession = Depends(get_db)) -> SurveyService:
    return SurveyService(db)

@router.get("/create", response_class=HTMLResponse)
async def create_survey_page(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        request=request,
        name="surveys/create.html",
        context={
            "user": user
        }
    )

@router.get("/partials/question", response_class=HTMLResponse)
async def get_question_partial(request: Request, index: int):
    return templates.TemplateResponse(
        request=request,
        name="partials/question_form.html",
        context={
            "index": index
        }
    )

@router.get("/partials/option", response_class=HTMLResponse)
async def get_option_partial(request: Request, q_index: int, o_index: int):
    return templates.TemplateResponse(
        request=request,
        name="partials/option_form.html",
        context={
            "q_index": q_index,
            "o_index": o_index
        }
    )

@router.post("/create")
async def create_survey(
    request: Request,
    user: User = Depends(get_current_user),
    service: SurveyService = Depends(get_survey_service)
):
    try:
        raw_data = await parse_form_data(request)
        survey_data = SurveyCreateForm(**raw_data)
        
        # Вся логика создания ушла в сервис
        await service.create_survey(user.user_id, survey_data)
        
    except ValidationError as e:
        error_msg = e.errors()[0]['msg'].replace("Value error, ", "") if e.errors() else str(e)
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка: {e}")

    return RedirectResponse(url="/?msg=survey_created", status_code=303)

@router.delete("/{survey_id}/delete")
async def delete_survey(
    request: Request,
    survey_id: int,
    user: User = Depends(get_current_user),
    service: SurveyService = Depends(get_survey_service)
):
    # Логика удаления
    await service.delete_survey(user, survey_id)

    # Получение обновленных данных для HTMX (также через сервис)
    created_count, taken_responses = await service.get_user_stats(user.user_id)
    taken_count = len(taken_responses)

    # Формирование HTML (Оставляем в роутере, так как это представление)
    content = ""
    content += f'<p id="created-count" hx-swap-oob="true" class="text-3xl font-bold text-green-600 mt-2">{created_count}</p>'
    content += f'<p id="taken-count" hx-swap-oob="true" class="text-3xl font-bold text-blue-600 mt-2">{taken_count}</p>'
    
    history_items = ""
    if taken_responses:
        for resp in taken_responses:
            status = "Завершен" if resp.completed_at else "Начат"
            status_color = "bg-green-100 text-green-700" if resp.completed_at else "bg-yellow-100 text-yellow-700"
            history_items += f"""
            <a href="/surveys/{resp.survey.survey_id}" class="flex justify-between items-center p-3 rounded-lg hover:bg-blue-50 transition border border-transparent hover:border-blue-100 group/item">
                <div>
                    <p class="font-medium text-gray-800 group-hover/item:text-blue-700">{resp.survey.title}</p>
                    <p class="text-xs text-gray-500">{resp.started_at.strftime('%d.%m.%Y')}</p>
                </div>
                <span class="text-xs font-semibold px-2 py-1 rounded {status_color}">{status}</span>
            </a>
            """
        history_html = f'<div id="history-list" hx-swap-oob="true"><div class="space-y-3">{history_items}</div></div>'
    else:
        history_html = '<div id="history-list" hx-swap-oob="true"><p class="text-gray-500 text-sm text-center py-4">Вы пока не проходили опросы.</p></div>'
    
    content += history_html
    return HTMLResponse(content=content, status_code=200, headers={"HX-Trigger": json.dumps({"showToast": "Опрос удален"})})