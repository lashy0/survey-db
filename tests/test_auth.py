import pytest
from httpx import AsyncClient
from sqlalchemy import select
from app.models import User
from app.core.security import get_password_hash

@pytest.mark.asyncio
async def test_register_user_success(client: AsyncClient, db_session):
    """Тест: Успешная регистрация нового пользователя"""
    payload = {
        "full_name": "Тестовый Пользователь",
        "email": "new_user@test.com",
        "password": "secret_password"
    }
    
    response = await client.post("/register", data=payload)
    
    # 1. Проверяем редирект на главную
    assert response.status_code == 302
    assert response.headers["location"] == "/"
    
    # 2. Проверяем наличие токенов в куках
    assert "access_token" in response.cookies
    assert "refresh_token" in response.cookies
    
    # 3. Проверяем, что пользователь реально создался в БД
    result = await db_session.execute(select(User).where(User.email == "new_user@test.com"))
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.full_name == "Тестовый Пользователь"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, db_session):
    """Тест: Попытка регистрации с уже существующим Email"""
    # Сначала создаем пользователя вручную
    existing_user = User(
        full_name="Existing",
        email="duplicate@test.com",
        password_hash=get_password_hash("123456"),
        country_id=1
    )
    db_session.add(existing_user)
    await db_session.commit()

    payload = {
        "full_name": "New Person",
        "email": "duplicate@test.com",
        "password": "password123"
    }
    
    response = await client.post("/register", data=payload)
    
    # Ожидаем ошибку 400 и сообщение в HTML
    assert response.status_code == 400
    assert "Email уже зарегистрирован" in response.text


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, db_session):
    """Тест: Успешный вход в систему"""
    # Создаем пользователя для входа
    user = User(
        full_name="Login Test",
        email="login@test.com",
        password_hash=get_password_hash("correct_password"),
        country_id=1
    )
    db_session.add(user)
    await db_session.commit()

    payload = {
        "email": "login@test.com",
        "password": "correct_password"
    }
    
    response = await client.post("/login", data=payload)
    
    assert response.status_code == 302
    assert "access_token" in response.cookies


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, db_session):
    """Тест: Вход с неверным паролем"""
    user = User(
        full_name="Security Test",
        email="security@test.com",
        password_hash=get_password_hash("secret"),
        country_id=1
    )
    db_session.add(user)
    await db_session.commit()

    payload = {
        "email": "security@test.com",
        "password": "WRONG_password"
    }
    
    response = await client.post("/login", data=payload)
    
    # Ожидаем 401 и текст ошибки
    assert response.status_code == 401
    assert "Неверный email или пароль" in response.text


@pytest.mark.asyncio
async def test_logout(client: AsyncClient):
    """Тест: Выход из системы (удаление кук)"""
    response = await client.get("/logout")
    
    assert response.status_code == 302
    # В ответе куки должны быть помечены на удаление
    assert response.cookies.get("access_token") is None