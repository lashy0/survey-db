import pytest
from httpx import AsyncClient
from sqlalchemy import select
from app.models import Survey, Question, Option, SurveyResponse, UserAnswer, SurveyStatus, QuestionType

@pytest.fixture
async def sample_survey(db_session, admin_token_cookies):
    """Фикстура: создает опрос с одним вопросом и двумя опциями"""
    survey = Survey(
        title="Тестовый опрос",
        description="Для проверки участия",
        status=SurveyStatus.active
    )
    db_session.add(survey)
    await db_session.flush()

    question = Question(
        survey_id=survey.survey_id,
        question_text="Твой выбор?",
        question_type=QuestionType.single_choice,
        is_required=True
    )
    db_session.add(question)
    await db_session.flush()

    opt1 = Option(question_id=question.question_id, option_text="Вариант А")
    opt2 = Option(question_id=question.question_id, option_text="Вариант Б")
    db_session.add_all([opt1, opt2])
    await db_session.commit()
    
    return survey, question, [opt1, opt2]


@pytest.mark.asyncio
async def test_submit_survey_success(client: AsyncClient, db_session, admin_token_cookies, sample_survey):
    """Тест: Успешная отправка ответа на опрос"""
    survey, question, options = sample_survey
    client.cookies.update(admin_token_cookies)

    # Данные формы: ключ q_{id_вопроса}, значение id_опции
    payload = {
        f"q_{question.question_id}": str(options[0].option_id)
    }
    
    response = await client.post(f"/surveys/{survey.survey_id}/submit", data=payload)
    
    # 1. Проверяем редирект обратно на страницу опроса с флагом успеха
    assert response.status_code == 303
    assert f"/surveys/{survey.survey_id}?msg=saved" in response.headers["location"]

    # 2. Проверяем, что в базе создалась сессия (SurveyResponse)
    res_query = await db_session.execute(select(SurveyResponse).where(SurveyResponse.survey_id == survey.survey_id))
    survey_response = res_query.scalar_one_or_none()
    assert survey_response is not None

    # 3. Проверяем, что ответ (UserAnswer) сохранен верно
    ans_query = await db_session.execute(select(UserAnswer).where(UserAnswer.response_id == survey_response.response_id))
    answer = ans_query.scalar_one_or_none()
    assert answer.selected_option_id == options[0].option_id


@pytest.mark.asyncio
async def test_submit_missing_required_question(client: AsyncClient, admin_token_cookies, sample_survey):
    """Тест: Ошибка при пропуске обязательного вопроса"""
    survey, _, _ = sample_survey
    client.cookies.update(admin_token_cookies)

    # Отправляем пустую форму
    payload = {}
    
    response = await client.post(f"/surveys/{survey.survey_id}/submit", data=payload)
    
    # Ожидаем 400 Bad Request и сообщение об ошибке
    assert response.status_code == 400
    assert "обязателен" in response.text


@pytest.mark.asyncio
async def test_submit_to_completed_survey_error(client: AsyncClient, db_session, admin_token_cookies):
    """Тест: Запрет отправки ответа в завершенный опрос"""
    # 1. Создаем завершенный опрос
    survey = Survey(title="Архивный опрос", status=SurveyStatus.completed)
    db_session.add(survey)
    await db_session.commit()

    client.cookies.update(admin_token_cookies)
    
    response = await client.post(f"/surveys/{survey.survey_id}/submit", data={})
    
    # Ожидаем 400 и текст из SurveyService
    assert response.status_code == 400
    assert "Опрос не активен" in response.text