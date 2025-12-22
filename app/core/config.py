from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn, computed_field
from sqlalchemy.engine import URL

# Load environment variables from .env file
load_dotenv()

class Settings(BaseSettings):
    # Pydantic сам считает переменные окружения, приведет типы и проверит их наличие
    DB_USER: str = "postgres"
    DB_PASS: str = ""
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "postgres"
    
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_ignore_empty=True,
        arbitrary_types_allowed=True 
    )

    @computed_field
    def database_url(self) -> URL:
        is_local = self.DB_HOST in ("localhost", "127.0.0.1")
        ssl_mode = "disable" if is_local else "require"
        # Создаем URL объект, который сам экранирует пароли
        url_object = URL.create(
            drivername="postgresql+asyncpg",
            username=self.DB_USER,
            password=self.DB_PASS,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
            query={"ssl": ssl_mode},  # Enforce SSL for production/cloud DBs
        )

        return url_object

settings = Settings()