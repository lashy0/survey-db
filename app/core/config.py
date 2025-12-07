import os
from dotenv import load_dotenv
from sqlalchemy.engine import URL

# Load environment variables from .env file
load_dotenv()

class Settings:
    """
    Application configuration settings.
    
    Attributes:
        DB_USER (str): Database username.
        DB_PASS (str): Database password.
        DB_HOST (str): Database hostname.
        DB_PORT (int): Database port.
        DB_NAME (str): Database name.
    """
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASS: str = os.getenv("DB_PASS", "")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", 5432))
    DB_NAME: str = os.getenv("DB_NAME", "postgres")

    # Auth settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-key-change-it-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    @property
    def database_url(self) -> URL:
        """
        Constructs the SQLAlchemy database URL object.

        This method safely handles special characters in passwords and 
        ensures SSL is enabled for cloud databases.

        Returns:
            URL: The constructed SQLAlchemy connection URL.
        """
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.DB_USER,
            password=self.DB_PASS,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
            query={"ssl": "require"},  # Enforce SSL for production/cloud DBs
        )

settings = Settings()