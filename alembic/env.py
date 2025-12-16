import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine # <--- ИЗМЕНЕНИЕ 1

from alembic import context

# Импорты вашего проекта
from app.core.config import settings
from app.models import Base

config = context.config

# Логирование
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = str(settings.database_url) # Для оффлайн режима строка ок
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    
    # --- ИЗМЕНЕНИЕ 2: Создаем движок напрямую из объекта настроек ---
    # Мы передаем settings.database_url как ОБЪЕКТ, а не строку. 
    # Это сохраняет пароль в исходном виде и не ломает спецсимволы.
    connectable = create_async_engine(
        settings.database_url,
        poolclass=pool.NullPool,
    )
    # ---------------------------------------------------------------

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())