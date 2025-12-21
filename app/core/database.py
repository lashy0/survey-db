from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

# Initialize the asynchronous engine
engine = create_async_engine(
    settings.database_url,
    echo=False,  # Set to False in production to reduce log noise
    pool_pre_ping=True,
    pool_size=2,
    max_overflow=0,
    pool_timeout=10
)

# Factory for creating new database sessions
async_session_maker = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False
)

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency generator that yields a database session.

    This function is designed to be used with FastAPI's Depends().
    It ensures the session is closed after the request is processed.

    Yields:
        AsyncSession: An asynchronous database session.
    """
    async with async_session_maker() as session:
        yield session