from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Anvero Backend"
    API_V1_STR: str = "/api/v1"
    
    # Konfiguracja bazy danych PostgreSQL (uzupełnisz swoimi danymi w pliku .env)
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "anvero_db"

    class Config:
        env_file = ".env"

settings = Settings()