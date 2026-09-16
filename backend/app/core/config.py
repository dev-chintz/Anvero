from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str = Field(default="Anvero API")
    app_version: str = Field(default="0.1.0")

    environment: Literal["development", "test", "production"] = "development"
    debug: bool = True

    host: str = "127.0.0.1"
    port: int = 8000

    api_v1_prefix: str = "/api/v1"

    database_url: str = Field(default="")
    secret_key: str = Field(default="")

    rate_limit_max_attempts: int = Field(default=5)
    rate_limit_window_seconds: int = Field(default=60)

    cors_origins: list[str] = Field(default=["http://localhost:3000"])

    model_config = SettingsConfigDict(
        env_file=BASE_DIR.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        """Require SECRET_KEY in production."""
        environment = info.data.get("environment", "development")
        if environment == "production" and not v:
            raise ValueError("SECRET_KEY is required in production environment")
        return v


settings = Settings()
