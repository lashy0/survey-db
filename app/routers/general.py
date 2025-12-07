from typing import Optional, Dict, Any
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import get_optional_user, get_current_user
from app.models import Survey, User, Question, SurveyResponse, UserAnswer, SurveyStatus, QuestionType

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def read_root(
    request: Request, 
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user)
) -> HTMLResponse:
    """
    Renders the homepage with a list of available surveys.

    Args:
        request (Request): The raw HTTP request object (required for Jinja2).
        db (AsyncSession): Database session dependency.

    Returns:
        HTMLResponse: The rendered 'index.html' template.
    """
    query = (
        select(Survey)
        .where(Survey.status != SurveyStatus.draft)
        .options(selectinload(Survey.tags))
        .order_by(Survey.created_at.desc())
    )
    result = await db.execute(query)
    surveys = result.scalars().all()

    return templates.TemplateResponse(
        name="index.html", 
        context={
            "request": request, 
            "surveys": surveys,
            "user": user
        }
    )


@router.get("/surveys/{survey_id}", response_class=HTMLResponse)
async def take_survey_page(
    survey_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user)
):
    query = (
        select(Survey)
        .where(Survey.survey_id == survey_id)
        .options(
            selectinload(Survey.tags),
            selectinload(Survey.author),
            selectinload(Survey.questions).selectinload(Question.options)
        )
    )
    result = await db.execute(query)
    survey = result.scalar_one_or_none()

    if not survey or survey.status == SurveyStatus.draft:
        raise HTTPException(status_code=404, detail="Quastion not found")
    
    survey.questions.sort(key=lambda q: q.position)

    user_response = None
    existing_answers: Dict[int, Any] = {}

    if user:
        resp_query = (
            select(SurveyResponse)
            .where(
                SurveyResponse.survey_id == survey_id,
                SurveyResponse.user_id == user.user_id
            )
            .options(selectinload(SurveyResponse.answers)) # Грузим ответы
        )
        resp_result = await db.execute(resp_query)
        user_response = resp_result.scalar_one_or_none()

        if user_response:
            for ans in user_response.answers:
                qid = ans.question_id
                
                if qid not in existing_answers:
                    existing_answers[qid] = []
                
                if ans.text_answer:
                    existing_answers[qid].append(ans.text_answer)
                elif ans.selected_option_id:
                    existing_answers[qid].append(ans.selected_option_id)
    
    is_readonly = survey.status in [SurveyStatus.completed, SurveyStatus.archived]

    return templates.TemplateResponse(
        "survey_detail.html",
        {
            "request": request,
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
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    # 1. Проверка опроса
    survey = await db.get(Survey, survey_id)
    if not survey or survey.status != SurveyStatus.active:
        raise HTTPException(status_code=400, detail="Этот опрос нельзя пройти сейчас")

    # 2. Получаем или создаем сессию (Response)
    # Используем unique constraint (user_id, survey_id)
    query = (
        select(SurveyResponse)
        .where(
            SurveyResponse.survey_id == survey_id,
            SurveyResponse.user_id == user.user_id
        )
        .options(selectinload(SurveyResponse.answers)) # Подгружаем старые ответы для сравнения
    )
    response_obj = (await db.execute(query)).scalar_one_or_none()

    if not response_obj:
        response_obj = SurveyResponse(
            survey_id=survey_id,
            user_id=user.user_id,
            started_at=datetime.now(timezone.utc),
            ip_address=request.client.host,
            device_type="Web"
        )
        db.add(response_obj)
        await db.flush() # Чтобы получить response_id
    
    # 3. Обработка формы
    form_data = await request.form()
    
    # Чтобы не делать N запросов, загрузим все вопросы опроса
    questions_map = {
        q.question_id: q 
        for q in (await db.execute(select(Question).where(Question.survey_id == survey_id))).scalars().all()
    }

    # Группируем ответы пользователя по вопросам из базы
    # (потому что мы не хотим доверять keys из формы слепо)
    
    for q_id, question in questions_map.items():
        form_key = f"q_{q_id}"
        
        # Получаем данные из формы (list для checkbox, str для остального)
        if question.question_type == QuestionType.multiple_choice:
            raw_values = form_data.getlist(form_key) # Список ID опций
        else:
            val = form_data.get(form_key)
            raw_values = [val] if val else []

        # Стратегия обновления
        
        if question.question_type == QuestionType.multiple_choice:
            # Для множественного выбора: проще удалить старые и записать новые
            # (так как сравнение списков "что добавить, что удалить" сложнее)
            
            # 1. Удаляем старые ответы на ЭТОТ вопрос
            await db.execute(
                delete(UserAnswer).where(
                    UserAnswer.response_id == response_obj.response_id,
                    UserAnswer.question_id == q_id
                )
            )
            
            # 2. Вставляем новые
            for opt_id in raw_values:
                if opt_id: # Проверка на пустоту
                    db.add(UserAnswer(
                        response_id=response_obj.response_id,
                        question_id=q_id,
                        selected_option_id=int(opt_id)
                    ))

        else:
            # Для Single Choice / Text / Rating: ищем СУЩЕСТВУЮЩИЙ ответ и обновляем его
            # (чтобы не растить id в таблице)
            
            current_answer_row = next(
                (a for a in response_obj.answers if a.question_id == q_id), 
                None
            )

            new_value = raw_values[0] if raw_values else None

            if new_value:
                if not current_answer_row:
                    # Создаем новый
                    current_answer_row = UserAnswer(
                        response_id=response_obj.response_id,
                        question_id=q_id
                    )
                    db.add(current_answer_row)
                
                # Обновляем поля
                if question.question_type == QuestionType.text_answer:
                    current_answer_row.text_answer = str(new_value)
                    current_answer_row.selected_option_id = None
                else:
                    current_answer_row.selected_option_id = int(new_value)
                    current_answer_row.text_answer = None
            else:
                # Если пользователь стер ответ (например, текст), можно удалить строку
                if current_answer_row:
                    await db.delete(current_answer_row)

    # 4. Финализация
    response_obj.completed_at = datetime.now(timezone.utc)
    await db.commit()

    # Редирект обратно на опрос с сообщением
    return RedirectResponse(
        url=f"/surveys/{survey_id}?msg=saved", 
        status_code=303
    )