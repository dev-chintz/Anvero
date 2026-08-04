from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()
