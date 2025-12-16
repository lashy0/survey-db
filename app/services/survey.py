from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any, Union
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from sqlalchemy.orm import selectinload

from app.models import (
    User, Survey, Question, Option, Tag, 
    SurveyResponse, UserAnswer, SurveyStatus, QuestionType, UserRole
)
from app.schemas import SurveyCreateForm
from app.core.security import get_password_hash # Если нужно, но тут вряд ли

class SurveyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_surveys(self) -> List[Survey]:
        """Получает список активных опросов для главной страницы."""
        query = (
            select(Survey)
            .where(Survey.status != SurveyStatus.draft)
            .options(selectinload(Survey.tags))
            .order_by(Survey.created_at.desc())
        )
        return (await self.db.execute(query)).scalars().all()

    async def get_survey_details(self, survey_id: int, user_id: Optional[int] = None):
        """
        Получает полную информацию об опросе для прохождения.
        Возвращает: survey, user_response (если есть), existing_answers (dict)
        """
        query = (
            select(Survey)
            .where(Survey.survey_id == survey_id)
            .options(
                selectinload(Survey.tags),
                selectinload(Survey.author),
                selectinload(Survey.questions).selectinload(Question.options)
            )
        )
        survey = (await self.db.execute(query)).scalar_one_or_none()
        
        if not survey or survey.status == SurveyStatus.draft:
            return None, None, None

        # Сортируем вопросы
        survey.questions.sort(key=lambda q: q.position)
        
        user_response = None
        existing_answers = {}
        
        if user_id:
            resp_query = (
                select(SurveyResponse)
                .where(
                    SurveyResponse.survey_id == survey_id,
                    SurveyResponse.user_id == user_id
                )
                .options(selectinload(SurveyResponse.answers))
            )
            user_response = (await self.db.execute(resp_query)).scalar_one_or_none()
            
            if user_response:
                for ans in user_response.answers:
                    qid = ans.question_id
                    if qid not in existing_answers:
                        existing_answers[qid] = []
                    
                    if ans.text_answer:
                        existing_answers[qid].append(ans.text_answer)
                    elif ans.selected_option_id:
                        existing_answers[qid].append(ans.selected_option_id)

        return survey, user_response, existing_answers

    async def create_survey(self, user_id: int, form: SurveyCreateForm) -> Survey:
        """Создает опрос, теги, вопросы и опции из Pydantic модели."""
        # 1. Опрос
        new_survey = Survey(
            title=form.title,
            description=form.description,
            status=SurveyStatus.active,
            author_id=user_id,
            created_at=datetime.now(timezone.utc),
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) + timedelta(days=30)
        )

        # 2. Теги
        if form.tag_names:
            final_tags = []
            for name in form.tag_names:
                name = name.strip()
                if not name: continue
                # Ищем существующий тег или создаем новый
                tag = (await self.db.execute(select(Tag).where(Tag.name == name))).scalar_one_or_none()
                if not tag:
                    tag = Tag(name=name)
                    self.db.add(tag)
                final_tags.append(tag)
            new_survey.tags = final_tags

        self.db.add(new_survey)
        await self.db.flush() # Получаем ID опроса

        # 3. Вопросы
        for q_item in form.questions:
            if not q_item.text: continue

            question = Question(
                survey_id=new_survey.survey_id,
                question_text=q_item.text,
                question_type=QuestionType(q_item.type),
                position=q_item.position,
                is_required=q_item.is_required
            )
            self.db.add(question)
            await self.db.flush() # Получаем ID вопроса

            # Опции
            if q_item.type in ["single_choice", "multiple_choice"]:
                for opt_text in q_item.options:
                    self.db.add(Option(question_id=question.question_id, option_text=opt_text))
            
            elif q_item.type == "rating":
                max_val = q_item.rating_scale if q_item.rating_scale else 5
                for i in range(1, max_val + 1):
                    self.db.add(Option(question_id=question.question_id, option_text=str(i)))

        await self.db.commit()
        return new_survey

    async def delete_survey(self, user: User, survey_id: int):
        """Удаляет опрос с проверкой прав."""
        survey = await self.db.get(Survey, survey_id)
        if not survey:
            raise HTTPException(status_code=404, detail="Опрос не найден")
        
        if survey.author_id != user.user_id and user.role != UserRole.admin:
            raise HTTPException(status_code=403, detail="Нет прав на удаление")
        
        await self.db.delete(survey)
        await self.db.commit()

    async def get_user_stats(self, user_id: int):
        """Возвращает статистику для обновления UI после удаления."""
        created_count = await self.db.scalar(
            select(func.count()).select_from(Survey).where(Survey.author_id == user_id)
        )
        taken_query = (
            select(SurveyResponse)
            .where(SurveyResponse.user_id == user_id)
            .options(selectinload(SurveyResponse.survey))
            .order_by(SurveyResponse.started_at.desc())
        )
        taken_responses = (await self.db.execute(taken_query)).scalars().all()
        return created_count, taken_responses

    async def process_survey_submission(self, user: User, survey_id: int, form_data: Any, client_host: str):
        """Валидирует ответы и сохраняет их в БД."""
        
        # 1. Загрузка данных
        survey_query = (
            select(Survey)
            .where(Survey.survey_id == survey_id)
            .options(selectinload(Survey.questions).selectinload(Question.options))
        )
        survey = (await self.db.execute(survey_query)).scalar_one_or_none()

        if not survey:
            raise HTTPException(status_code=404, detail="Опрос не найден")
        if survey.status != SurveyStatus.active:
            raise HTTPException(status_code=400, detail="Опрос не активен")

        # --- ВАЛИДАЦИЯ ---
        cleaned_data = {}
        
        for question in survey.questions:
            form_key = f"q_{question.question_id}"
            
            # Извлекаем данные (учитываем, что multiple_choice - это список)
            if question.question_type == QuestionType.multiple_choice:
                raw_values = form_data.getlist(form_key)
            else:
                val = form_data.get(form_key)
                raw_values = [val] if val else []

            # Чистим от пустых строк
            raw_values = [v for v in raw_values if v is not None and str(v).strip() != ""]

            # Проверка обязательности
            if question.is_required and not raw_values:
                raise HTTPException(status_code=400, detail=f"Вопрос '{question.question_text}' обязателен")

            if not raw_values: continue

            # Проверка валидности значений
            valid_values = []
            if question.question_type in [QuestionType.single_choice, QuestionType.multiple_choice, QuestionType.rating]:
                valid_ids = {str(opt.option_id) for opt in question.options}
                for val in raw_values:
                    if val not in valid_ids:
                        raise HTTPException(status_code=400, detail=f"Некорректный вариант для '{question.question_text}'")
                    valid_values.append(int(val))
            
            elif question.question_type == QuestionType.text_answer:
                text_val = str(raw_values[0]).strip()
                if len(text_val) > 5000:
                    raise HTTPException(status_code=400, detail=f"Ответ на вопрос '{question.question_text}' слишком длинный")
                valid_values.append(text_val)

            cleaned_data[question.question_id] = {
                "type": question.question_type,
                "values": valid_values
            }

        # --- СОХРАНЕНИЕ ---
        # Получаем/Создаем сессию
        query = (
            select(SurveyResponse)
            .where(SurveyResponse.survey_id == survey_id, SurveyResponse.user_id == user.user_id)
            .options(selectinload(SurveyResponse.answers))
        )
        response_obj = (await self.db.execute(query)).scalar_one_or_none()
        
        if not response_obj:
            response_obj = SurveyResponse(
                survey_id=survey_id, user_id=user.user_id,
                started_at=datetime.now(timezone.utc),
                ip_address=client_host, device_type="Web"
            )
            self.db.add(response_obj)
            await self.db.flush()

        response_obj.completed_at = datetime.now(timezone.utc)

        # Сохранение ответов
        for q_id, data in cleaned_data.items():
            q_type = data["type"]
            values = data["values"]

            # Для мульти-выбора: удаляем старые, пишем новые
            if q_type == QuestionType.multiple_choice:
                await self.db.execute(delete(UserAnswer).where(
                    UserAnswer.response_id == response_obj.response_id,
                    UserAnswer.question_id == q_id
                ))
                for val in values:
                    self.db.add(UserAnswer(response_id=response_obj.response_id, question_id=q_id, selected_option_id=val))
            
            else:
                # Ищем существующий
                existing_ans = None
                if response_obj.answers:
                    for ans in response_obj.answers:
                        if ans.question_id == q_id:
                            existing_ans = ans; break
                
                if not values:
                    if existing_ans: await self.db.delete(existing_ans)
                    continue

                val = values[0]
                if not existing_ans:
                    existing_ans = UserAnswer(response_id=response_obj.response_id, question_id=q_id)
                    self.db.add(existing_ans)

                if q_type == QuestionType.text_answer:
                    existing_ans.text_answer = val
                    existing_ans.selected_option_id = None
                else:
                    existing_ans.selected_option_id = val
                    existing_ans.text_answer = None

        # Очистка сирот (ответов на вопросы, которые перестали быть заполненными)
        answered_q_ids = set(cleaned_data.keys())
        if response_obj.answers:
            for ans in response_obj.answers:
                if ans.question_id not in answered_q_ids:
                    await self.db.delete(ans)

        await self.db.commit()