import pytest
from httpx import AsyncClient
from sqlalchemy import select
from app.models import Survey, User, UserRole
from app.core.security import get_password_hash, create_access_token

@pytest.mark.asyncio
async def test_create_survey_success(client: AsyncClient, db_session, admin_token_cookies):
    """Тест: Успешное создание опроса администратором"""
    client.cookies.update(admin_token_cookies)
    
    # Имитируем структуру данных из HTML-формы (как ее ждет app/core/utils.py)
    payload = {
        "title": "Новый аналитический опрос",
        "description": "Описание тестового опроса",
        "tag_names": ["IT", "Data"],
        "questions[0][text]": "Ваш любимый язык?",
        "questions[0][type]": "single_choice",
        "questions[0][options][0]": "Python",
        "questions[0][options][1]": "SQL",
        "questions[0][position]": "1",
        "questions[0][is_required]": "on"
    }
    
    response = await client.post("/surveys/create", data=payload)
    
    # Проверяем редирект
    assert response.status_code == 303
    assert response.headers["location"] == "/?msg=survey_created"
    
    # Проверяем в базе
    result = await db_session.execute(select(Survey).where(Survey.title == "Новый аналитический опрос"))
    survey = result.scalar_one_or_none()
    assert survey is not None
    assert survey.description == "Описание тестового опроса"


@pytest.mark.asyncio
async def test_create_survey_no_questions_error(client: AsyncClient, admin_token_cookies):
    """Тест: Ошибка при создании опроса без вопросов"""
    client.cookies.update(admin_token_cookies)
    
    # Отправляем только заголовок и описание
    payload = {
        "title": "Пустой опрос",
        "description": "Без вопросов"
    }
    
    response = await client.post("/surveys/create", data=payload)
    
    # Ожидаем 400 (так как в схемах SurveyCreateForm стоит валидатор на наличие вопросов)
    assert response.status_code == 400
    assert "Опрос должен содержать хотя бы один вопрос" in response.text


@pytest.mark.asyncio
async def test_delete_survey_unauthorized(client: AsyncClient, db_session):
    """Тест: Запрет удаления чужого опроса обычным пользователем"""
    # 1. Создаем Владельца и его опрос
    owner = User(full_name="Owner", email="owner@test.com", password_hash="hash", country_id=1)
    db_session.add(owner)
    await db_session.flush()
    
    survey = Survey(title="Чужой опрос", author_id=owner.user_id)
    db_session.add(survey)
    await db_session.commit()
    await db_session.refresh(survey)

    # 2. Создаем Хакера и логинимся под ним
    hacker = User(full_name="Hacker", email="hacker@test.com", password_hash=get_password_hash("123456"), country_id=1, role=UserRole.user)
    db_session.add(hacker)
    await db_session.commit()
    
    token = create_access_token(data={"sub": hacker.email})
    client.cookies.set("access_token", token)

    # 3. Пытаемся удалить опрос владельца
    response = await client.delete(f"/surveys/{survey.survey_id}/delete")
    
    # Ожидаем 403 Forbidden
    assert response.status_code == 403
    assert "Нет прав на удаление" in response.text


@pytest.mark.asyncio
async def test_admin_can_delete_any_survey(client: AsyncClient, db_session, admin_token_cookies):
    """Тест: Администратор может удалить любой опрос"""
    # 1. Создаем опрос обычного юзера
    survey = Survey(title="Опрос юзера", author_id=None)
    db_session.add(survey)
    await db_session.commit()
    await db_session.refresh(survey)

    # 2. Авторизуемся как админ
    client.cookies.update(admin_token_cookies)

    # 3. Удаляем
    response = await client.delete(f"/surveys/{survey.survey_id}/delete")
    
    # Успех удаления через HTMX возвращает 200 и спец. заголовки
    assert response.status_code == 200
    assert "showToast" in response.headers["HX-Trigger"]