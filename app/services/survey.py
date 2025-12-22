from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any, Union
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, extract, desc, text
from sqlalchemy.orm import selectinload

from app.models import (
    User, Survey, Question, Option, Tag, 
    SurveyResponse, UserAnswer, SurveyStatus, QuestionType, UserRole,
    survey_tags
)
from app.schemas import SurveyCreateForm


class SurveyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_public_surveys(self) -> List[Survey]:
        """Получает список ВСЕХ публичных опросов (активные + завершенные)."""
        query = (
            select(Survey)
            .where(Survey.status != SurveyStatus.draft) # Исключаем только черновики
            .options(selectinload(Survey.tags))
            .order_by(Survey.created_at.desc())
        )
        return (await self.db.execute(query)).scalars().all()

    async def get_survey_details(self, survey_id: int, user: Optional[User] = None):
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
        
        if not survey:
            return None, None, None
            
        if survey.status == SurveyStatus.draft:
            # Разрешаем, если пользователь - автор ИЛИ админ
            allowed = False
            if user:
                if user.role == UserRole.admin or user.user_id == survey.author_id:
                    allowed = True
            
            if not allowed:
                return None, None, None

        # Сортируем вопросы
        survey.questions.sort(key=lambda q: q.position)
        
        user_response = None
        existing_answers = {}
        
        if user:
            resp_query = (
                select(SurveyResponse)
                .where(
                    SurveyResponse.survey_id == survey_id,
                    SurveyResponse.user_id == user.user_id
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
            if question.question_type == QuestionType.multiple_choice:
                raw_values = form_data.getlist(form_key)
            else:
                val = form_data.get(form_key)
                raw_values = [val] if val else []

            raw_values = [v for v in raw_values if v is not None and str(v).strip() != ""]

            if question.is_required and not raw_values:
                raise HTTPException(status_code=400, detail=f"Вопрос '{question.question_text}' обязателен")
            
            if not raw_values: continue

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
                    raise HTTPException(status_code=400, detail=f"Ответ слишком длинный")
                valid_values.append(text_val)

            cleaned_data[question.question_id] = {
                "type": question.question_type,
                "values": valid_values
            }

        # --- СОХРАНЕНИЕ ---
        # Получаем/Создаем сессию
        resp_query = select(SurveyResponse).where(
            SurveyResponse.survey_id == survey_id, 
            SurveyResponse.user_id == user.user_id
        )
        response_obj = (await self.db.execute(resp_query)).scalar_one_or_none()
        
        if not response_obj:
            response_obj = SurveyResponse(
                survey_id=survey_id, 
                user_id=user.user_id,
                started_at=datetime.now(timezone.utc),
                ip_address=client_host, 
                device_type="Web"
            )
            self.db.add(response_obj)
            await self.db.flush()
        else:
            await self.db.execute(
                delete(UserAnswer).where(UserAnswer.response_id == response_obj.response_id)
            )
        
        response_obj.completed_at = datetime.now(timezone.utc)

        for q_id, info in cleaned_data.items():
            for val in info["values"]:
                new_ans = UserAnswer(response_id=response_obj.response_id, question_id=q_id)
                if info["type"] == QuestionType.text_answer:
                    new_ans.text_answer = val
                else:
                    new_ans.selected_option_id = val
                self.db.add(new_ans)

        await self.db.commit()
    
    async def get_recommendations(self, user_id: int, limit: int = 3) -> List[Survey]:
        """
        Рекомендательная система (Упрощенная и надежная версия):
        """
        rec_query = select(text("*")).select_from(
            func.get_survey_recommendations(user_id).alias("recs")
        )
        
        result = await self.db.execute(rec_query)
        rows = result.all() # Получим список (survey_id, score)

        if not rows:
            # Если рекомендаций нет (Cold Start), возвращаем просто популярные опросы
            fallback_query = (
                select(Survey)
                .where(Survey.status == SurveyStatus.active)
                .options(selectinload(Survey.tags))
                .limit(limit)
            )
            return (await self.db.execute(fallback_query)).scalars().all()

        # 2. Получаем полные объекты Survey для найденных ID
        target_ids = [r.survey_id for r in rows[:limit]]
        
        final_surveys = (
            await self.db.execute(
                select(Survey)
                .where(Survey.survey_id.in_(target_ids))
                .options(selectinload(Survey.tags))
            )
        ).scalars().all()
        
        return final_surveys
    
    async def get_survey_analytics(self, survey_id: int):
        """
        Собирает детальную статистику по каждому вопросу опроса.
        """
        # 1. Загружаем сам опрос с вопросами и опциями
        survey = await self.db.get(Survey, survey_id)
        if not survey: return None
        
        # Подгружаем вопросы, чтобы знать их текст и тип
        q_query = select(Question).where(Question.survey_id == survey_id).order_by(Question.position).options(selectinload(Question.options))
        questions = (await self.db.execute(q_query)).scalars().all()
        
        analytics = []
        
        for q in questions:
            q_stats = {
                "id": q.question_id,
                "text": q.question_text,
                "type": q.question_type,
                "total_answers": 0,
                "data": None
            }
            
            # А. Для вопросов с выбором (Single/Multiple/Rating)
            if q.question_type in [QuestionType.single_choice, QuestionType.multiple_choice, QuestionType.rating]:
                # Считаем кол-во выборов для каждого варианта
                stats_query = (
                    select(Option.option_text, func.count(UserAnswer.answer_id).label('cnt'))
                    .join(UserAnswer, Option.option_id == UserAnswer.selected_option_id)
                    .where(Option.question_id == q.question_id)
                    .group_by(Option.option_text)
                    .order_by(desc('cnt'))
                )
                res = (await self.db.execute(stats_query)).all()
                
                labels = [row.option_text for row in res]
                counts = [row.cnt for row in res]
                total = sum(counts)
                
                q_stats["total_answers"] = total
                q_stats["data"] = {
                    "labels": labels,
                    "counts": counts,
                    "percentages": [round(c/total*100, 1) if total else 0 for c in counts]
                }
                
                # Доп. фича: Средний возраст для каждого варианта ответа (Инсайт!)
                # "Кто выбирает вариант А? Молодежь или старики?"
                age_query = (
                    select(
                        Option.option_text, 
                        func.avg(extract('year', func.age(User.birth_date))).label('avg_age')
                    )
                    .join(UserAnswer, Option.option_id == UserAnswer.selected_option_id)
                    .join(SurveyResponse, UserAnswer.response_id == SurveyResponse.response_id)
                    .join(User, SurveyResponse.user_id == User.user_id)
                    .where(Option.question_id == q.question_id)
                    .group_by(Option.option_text)
                )
                age_res = (await self.db.execute(age_query)).all()
                # Превращаем в словарь {Вариант: СреднийВозраст}
                age_map = {row.option_text: round(row.avg_age or 0, 1) for row in age_res}
                q_stats["data"]["avg_ages"] = [age_map.get(lbl, 0) for lbl in labels]

            # Б. Для текстовых вопросов
            elif q.question_type == QuestionType.text_answer:
                text_query = (
                    select(UserAnswer.text_answer, SurveyResponse.completed_at) # Добавили дату
                    .join(SurveyResponse, UserAnswer.response_id == SurveyResponse.response_id)
                    .where(UserAnswer.question_id == q.question_id, UserAnswer.text_answer.is_not(None))
                    .order_by(SurveyResponse.completed_at.desc())
                    .limit(50) # Увеличим лимит
                )
                res = (await self.db.execute(text_query)).all() # .all() вместо .scalars().all() т.к. два поля
                
                q_stats["total_answers"] = len(res)
                # Преобразуем в список словарей для удобства в шаблоне
                q_stats["data"] = [{"text": r.text_answer, "date": r.completed_at} for r in res]

            analytics.append(q_stats)
            
        return {"survey": survey, "questions": analytics}
    
    async def search_surveys(self, query_str: str) -> List[Survey]:
        """Умный поиск через SQL функцию."""
        if not query_str.strip():
            return await self.get_public_surveys()

        # 1. Вызываем функцию поиска
        stmt = select(text("survey_id")).select_from(
            func.search_surveys_ranked(query_str).alias("s")
        )
        result = await self.db.execute(stmt)
        ids = [row[0] for row in result.all()]

        if not ids:
            return []

        # 2. Подгружаем полные данные для найденных ID
        final_query = (
            select(Survey)
            .where(Survey.survey_id.in_(ids))
            .options(selectinload(Survey.tags))
        )
        surveys = (await self.db.execute(final_query)).scalars().all()
        
        # Сортируем в Python, чтобы сохранить порядок релевантности из SQL
        id_map = {id_: i for i, id_ in enumerate(ids)}
        return sorted(surveys, key=lambda s: id_map.get(s.survey_id))
