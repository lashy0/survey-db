import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    response = await client.get("/register")
    assert response.status_code == 200
    assert "Создать аккаунт" in response.text

@pytest.mark.asyncio
async def test_login_wrong_credentials(client: AsyncClient):
    payload = {
        "email": "non_existent@test.com",
        "password": "wrong"
    }
    # Теперь CSRF не мешает, запрос дойдет до роутера
    response = await client.post("/login", data=payload)
    
    # Роутер вернет 200 (страницу с ошибкой) или 401
    # Проверьте ваш код в auth.py. Обычно это 401.
    assert response.status_code == 401 
    assert "Неверный email или пароль" in response.text