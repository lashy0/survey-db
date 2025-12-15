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
    # 1. Загрузка данных опроса с вопросами и опциями
    # Важно: используем eager loading для опций, чтобы валидировать ID
    survey_query = (
        select(Survey)
        .where(Survey.survey_id == survey_id)
        .options(
            selectinload(Survey.questions).selectinload(Question.options)
        )
    )
    survey = (await db.execute(survey_query)).scalar_one_or_none()

    if not survey:
        raise HTTPException(status_code=404, detail="Опрос не найден")
    if survey.status != SurveyStatus.active:
        raise HTTPException(status_code=400, detail="Опрос не активен")

    form_data = await request.form()
    
    # --- ЭТАП 1: ВАЛИДАЦИЯ ---
    # Мы собираем очищенные данные, чтобы потом их сохранить
    # cleaned_data = { question_id: { 'type': ..., 'values': [...] } }
    cleaned_data = {}

    for question in survey.questions:
        form_key = f"q_{question.question_id}"
        
        # Получаем сырые данные
        if question.question_type == QuestionType.multiple_choice:
            raw_values = form_data.getlist(form_key) # Список строк
        else:
            val = form_data.get(form_key)
            raw_values = [val] if val else []

        # Фильтруем пустые строки
        raw_values = [v for v in raw_values if v is not None and str(v).strip() != ""]

        # 1. Проверка на обязательность
        if question.is_required and not raw_values:
            raise HTTPException(
                status_code=400, 
                detail=f"Вопрос '{question.question_text}' обязателен для ответа"
            )

        # Если ответ пустой и необязательный — пропускаем валидацию значений
        if not raw_values:
            continue

        # 2. Проверка валидности значений (защита от подделки ID)
        valid_values = []
        
        if question.question_type in [QuestionType.single_choice, QuestionType.multiple_choice, QuestionType.rating]:
            # Создаем множество валидных ID для этого вопроса
            valid_option_ids = {str(opt.option_id) for opt in question.options}
            
            for val in raw_values:
                if val not in valid_option_ids:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Получен некорректный вариант ответа для вопроса '{question.question_text}'"
                    )
                valid_values.append(int(val))
                
        elif question.question_type == QuestionType.text_answer:
            # Для текста просто сохраняем строку (можно добавить проверку на длину)
            text_val = str(raw_values[0]).strip()
            if len(text_val) > 5000: # Лимит на длину
                 raise HTTPException(status_code=400, detail=f"Ответ на вопрос '{question.question_text}' слишком длинный")
            valid_values.append(text_val)

        cleaned_data[question.question_id] = {
            "type": question.question_type,
            "values": valid_values
        }

    # --- ЭТАП 2: СОХРАНЕНИЕ ---
    
    # Получаем или создаем сессию (Response)
    query = (
        select(SurveyResponse)
        .where(
            SurveyResponse.survey_id == survey_id,
            SurveyResponse.user_id == user.user_id
        )
        .options(selectinload(SurveyResponse.answers))
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
        await db.flush() # Получаем ID
    
    # Обновляем время завершения
    response_obj.completed_at = datetime.now(timezone.utc)

    # Применяем изменения к ответам
    # Стратегия: идем по cleaned_data.
    # Если вопрос мульти-выбор -> удаляем старые, пишем новые.
    # Если одиночный/текст -> обновляем или создаем.
    
    for q_id, data in cleaned_data.items():
        q_type = data["type"]
        values = data["values"] # list of int (option_ids) or list of str (text)

        if q_type == QuestionType.multiple_choice:
            # Удаляем старые
            await db.execute(
                delete(UserAnswer).where(
                    UserAnswer.response_id == response_obj.response_id,
                    UserAnswer.question_id == q_id
                )
            )
            # Пишем новые
            for val in values:
                db.add(UserAnswer(
                    response_id=response_obj.response_id,
                    question_id=q_id,
                    selected_option_id=val
                ))
        
        else: # Single, Rating, Text
            # Ищем существующий ответ в памяти (так как мы подгрузили .answers)
            # или в БД, если объект свежий
            existing_ans = None
            if response_obj.answers:
                for ans in response_obj.answers:
                    if ans.question_id == q_id:
                        existing_ans = ans
                        break
            
            if not values:
                # Пользователь стер ответ (если он необязательный)
                if existing_ans:
                    await db.delete(existing_ans)
                continue

            val = values[0]
            
            if not existing_ans:
                existing_ans = UserAnswer(
                    response_id=response_obj.response_id, 
                    question_id=q_id
                )
                db.add(existing_ans)
            
            # Обновляем поля
            if q_type == QuestionType.text_answer:
                existing_ans.text_answer = val
                existing_ans.selected_option_id = None
            else:
                existing_ans.selected_option_id = val
                existing_ans.text_answer = None

    # Обработка случаев, когда пользователь очистил ответы на необязательные вопросы,
    # которых нет в cleaned_data (потому что form_data их не прислал)
    # Находим вопросы, на которые были ответы раньше, но теперь нет
    answered_q_ids = set(cleaned_data.keys())
    if response_obj.answers:
        for ans in response_obj.answers:
            if ans.question_id not in answered_q_ids:
                # Проверяем, действительно ли вопрос существует в этом опросе (на всякий случай)
                # и удаляем ответ
                await db.delete(ans)

    await db.commit()
    
    return RedirectResponse(
        url=f"/surveys/{survey_id}?msg=saved", 
        status_code=303
    )