import pytest
import asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

# Импортируем роутеры
from app.routers import general, admin, auth, users, surveys
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import check_csrf
from app.core.exceptions import (
    not_found_handler,
    forbidden_handler,
    server_error_handler,
    unauthorized_handler
)
from fastapi import FastAPI

# Создаем тестовый движок
# Используем NullPool, чтобы не было проблем с закрытием соединений между тестами
test_engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
    echo=False
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    expire_on_commit=False,
    join_transaction_mode="create_savepoint"
)

# --- ВАЖНОЕ ИЗМЕНЕНИЕ ---
# Мы НЕ создаем фикстуру event_loop вручную.
# Вместо этого мы говорим anyio использовать asyncio.
@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Создает сессию внутри транзакции.
    """
    connection = await test_engine.connect()
    transaction = await connection.begin()
    session = TestingSessionLocal(bind=connection)
    
    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()
        await asyncio.sleep(0.01)

@pytest.fixture(scope="function")
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """
    Создает тестовый клиент без Middleware.
    """
    # Создаем чистое приложение без middleware (чтобы избежать конфликтов циклов)
    test_app = FastAPI()

    test_app.add_exception_handler(404, not_found_handler)
    test_app.add_exception_handler(403, forbidden_handler)
    test_app.add_exception_handler(401, unauthorized_handler)
    test_app.add_exception_handler(500, server_error_handler)
    
    # Подключаем роутеры
    test_app.include_router(admin.router)
    test_app.include_router(auth.router)
    test_app.include_router(users.router)
    test_app.include_router(surveys.router)
    test_app.include_router(general.router)
    
    # Переопределяем зависимость БД
    async def override_get_db():
        yield db_session
    
    async def skip_csrf():
        pass
    
    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[check_csrf] = skip_csrf
    
    # Важно: не используем base_url с http://test, так как куки могут не ставиться
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://localhost") as ac:
        yield ac

@pytest.fixture
async def admin_token_cookies(db_session):
    from app.core.security import get_password_hash, create_access_token
    from app.models import User, UserRole
    
    email = f"admin_{asyncio.get_event_loop().time()}@test.com"
    
    admin = User(
        full_name="Test Admin",
        email=email,
        password_hash=get_password_hash("123456"),
        role=UserRole.admin,
        country_id=None
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    
    access_token = create_access_token(data={"sub": admin.email})
    return {"access_token": access_token}

@pytest.fixture(scope="session", autouse=True)
async def shutdown_test_engine():
    """
    Автоматически закрывает все соединения с базой данных 
    после завершения ВСЕХ тестов в сессии.
    """
    yield
    await test_engine.dispose()