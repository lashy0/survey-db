import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_survey_page_access(client: AsyncClient, admin_token_cookies):
    # 1. Без авторизации -> редирект или 401
    response = await client.get("/surveys/create")
    # У вас настроен редирект 303 на /login для 401 ошибки
    assert response.status_code in [401, 302, 303, 307]

    # 2. С авторизацией
    client.cookies.update(admin_token_cookies)
    response = await client.get("/surveys/create")
    assert response.status_code == 200
    assert "Новый опрос" in response.text

@pytest.mark.asyncio
async def test_admin_dashboard_access(client: AsyncClient, admin_token_cookies):
    # Устанавливаем куки авторизации
    client.cookies.update(admin_token_cookies)
    
    response = await client.get("/admin/analytics")
    assert response.status_code == 200
    assert "Аналитическая панель" in response.text