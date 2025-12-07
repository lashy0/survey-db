from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User, Survey, Question, Option, Tag, SurveyStatus, QuestionType

router = APIRouter(prefix="/surveys", tags=["surveys"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/create", response_class=HTMLResponse)
async def create_survey_page(
    request: Request,
    user: User = Depends(get_current_user)
):
    """Страница создания опроса."""
    
    return templates.TemplateResponse(
        "surveys/create.html", 
        {"request": request, "user": user}
    )

# --- HTMX: Динамическое добавление полей ---

@router.get("/partials/question", response_class=HTMLResponse)
async def get_question_partial(request: Request, index: int):
    """Возвращает HTML-блок нового вопроса."""
    return templates.TemplateResponse(
        "partials/question_form.html",
        {"request": request, "index": index}
    )

@router.get("/partials/option", response_class=HTMLResponse)
async def get_option_partial(request: Request, q_index: int, o_index: int):
    """Возвращает HTML-блок нового варианта ответа."""
    return templates.TemplateResponse(
        "partials/option_form.html",
        {"request": request, "q_index": q_index, "o_index": o_index}
    )

# --- Сохранение опроса ---

@router.post("/create")
async def create_survey(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    form_data = await request.form()
    
    # 1. Создаем Опрос
    new_survey = Survey(
        title=title,
        description=description,
        status=SurveyStatus.active, # Сразу активный для простоты
        author_id=user.user_id,
        created_at=datetime.now(timezone.utc),
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=30)
    )
    
    tag_names = form_data.getlist("tag_names")
    
    if tag_names:
        final_tags = []
        for name in tag_names:
            name = name.strip()
            if not name: continue
            
            # Ищем тег
            tag = (await db.execute(select(Tag).where(Tag.name == name))).scalar_one_or_none()
            if not tag:
                # Создаем новый
                tag = Tag(name=name)
                db.add(tag)
                # Нужно сделать flush, чтобы получить ID, если бы мы его использовали, 
                # но для relationshio достаточно объекта
            final_tags.append(tag)
        
        new_survey.tags = final_tags

    db.add(new_survey)
    await db.flush() # Получаем ID опроса

    # 2. Парсим вопросы из формы вручную
    # Формат имен полей: 
    #   questions[0][text]
    #   questions[0][type]
    #   questions[0][options][0]
    
    # Ищем индексы вопросов
    q_indexes = set()
    for key in form_data.keys():
        if key.startswith("questions[") and "][text]" in key:
            # Извлекаем индекс: questions[0][text] -> 0
            idx = int(key.split("[")[1].split("]")[0])
            q_indexes.add(idx)
    
    # Сортируем не по ID, а по скрытому полю position, которое заполнит JS
    # Создаем список кортежей (position, index)
    questions_to_create = []
    
    for idx in q_indexes:
        # Получаем позицию из формы, или 0 по дефолту
        pos_str = form_data.get(f"questions[{idx}][position]", "0")
        pos = int(pos_str) if pos_str.isdigit() else 0
        questions_to_create.append((pos, idx))
    
    # Сортируем по position
    questions_to_create.sort(key=lambda x: x[0])

    for loop_pos, (_, idx) in enumerate(questions_to_create, start=1):
        q_text = form_data.get(f"questions[{idx}][text]")
        q_type = form_data.get(f"questions[{idx}][type]")

        is_required_val = form_data.get(f"questions[{idx}][is_required]")
        is_required = True if is_required_val == "on" else False
        
        if not q_text: continue

        question = Question(
            survey_id=new_survey.survey_id,
            question_text=q_text,
            question_type=QuestionType(q_type),
            position=loop_pos,
            is_required=is_required
        )
        db.add(question)
        await db.flush()

        # Опции
        if q_type in ["single_choice", "multiple_choice"]:
            prefix = f"questions[{idx}][options]["
            o_indexes = set()
            for key in form_data.keys():
                if key.startswith(prefix):
                    o_idx = int(key.split(prefix)[1].split("]")[0])
                    o_indexes.add(o_idx)
            
            for o_idx in sorted(list(o_indexes)):
                opt_text = form_data.get(f"questions[{idx}][options][{o_idx}]")
                if opt_text:
                    db.add(Option(question_id=question.question_id, option_text=opt_text))
        
        elif q_type == "rating":
            # НОВАЯ ЛОГИКА: Генерируем цифры
            scale = form_data.get(f"questions[{idx}][rating_scale]", "5")
            max_val = int(scale) if scale.isdigit() else 5
            
            for i in range(1, max_val + 1):
                db.add(Option(question_id=question.question_id, option_text=str(i)))

    await db.commit()
    
    return RedirectResponse(url="/?msg=survey_created", status_code=303)