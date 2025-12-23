import pytest
from httpx import AsyncClient
from app.models import User, UserRole
from app.core.security import get_password_hash, create_access_token

@pytest.fixture
async def user_token_cookies(db_session):
    """Фикстура: создает ОБЫЧНОГО пользователя и возвращает его токены"""
    email = "regular_user@test.com"
    user = User(
        full_name="Обычный Юзер",
        email=email,
        password_hash=get_password_hash("123456"),
        role=UserRole.user, # Важно: роль USER
        country_id=None
    )
    db_session.add(user)
    await db_session.commit()
    
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token}


@pytest.mark.asyncio
async def test_admin_page_forbidden_for_regular_user(client: AsyncClient, user_token_cookies):
    """Тест: Обычный пользователь получает 403 при попытке зайти в админку"""
    client.cookies.update(user_token_cookies)
    
    # Пытаемся зайти в аналитику
    response = await client.get("/admin/analytics")
    
    # Ожидаем 403 Forbidden
    assert response.status_code == 403
    assert "Доступ запрещен" in response.text


@pytest.mark.asyncio
async def test_admin_page_accessible_for_admin(client: AsyncClient, admin_token_cookies):
    """Тест: Администратор имеет доступ к админке"""
    client.cookies.update(admin_token_cookies)
    
    response = await client.get("/admin/analytics")
    
    # Ожидаем 200 OK
    assert response.status_code == 200
    assert "Аналитическая панель" in response.text


@pytest.mark.asyncio
async def test_profile_page_redirects_anonymous(client: AsyncClient):
    """Тест: Анонимного пользователя не пускает в профиль (401 или редирект)"""
    # Не устанавливаем никаких кук
    response = await client.get("/users/me")
    
    # Согласно вашей логике в deps.py, выкидывается 401
    assert response.status_code == 401
    assert "Требуется авторизация" in response.text


@pytest.mark.asyncio
async def test_database_tables_forbidden_for_user(client: AsyncClient, user_token_cookies):
    """Тест: Обычный пользователь не может видеть список таблиц БД"""
    client.cookies.update(user_token_cookies)
    
    response = await client.get("/admin/tables_view")
    
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_user_can_access_own_profile(client: AsyncClient, user_token_cookies):
    """Тест: Авторизованный пользователь может зайти в свой личный кабинет"""
    client.cookies.update(user_token_cookies)
    
    response = await client.get("/users/me")
    
    assert response.status_code == 200
    assert "Личный кабинет" in response.text