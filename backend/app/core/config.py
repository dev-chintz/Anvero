from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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

    # slowapi limit string format, e.g. "5/minute". See https://limits.readthedocs.io/en/stable/quickstart.html#rate-limit-string-notation
    rate_limit_login: str = Field(default="5/minute")

    # IANA zone the business works in. Timestamps are stored in UTC, but a
    # date filter such as "11 September" means that calendar day here, not
    # in UTC, or orders placed just after local midnight fall on the wrong day.
    business_timezone: str = Field(default="Europe/Warsaw")

    # Allegro integration. Reading orders needs a token issued in a user
    # context, so the refresh token comes from a one-time authorization
    # performed by hand; see docs/INTEGRATIONS.md. Empty values leave the
    # integration switched off rather than failing at import time.
    allegro_client_id: str = Field(default="")
    allegro_client_secret: str = Field(default="")
    allegro_refresh_token: str = Field(default="")
    allegro_api_url: str = Field(default="https://api.allegro.pl")
    allegro_auth_url: str = Field(default="https://allegro.pl/auth/oauth")

    @field_validator("business_timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        # fail at startup rather than on the first filtered request
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone: {value!r}") from exc
        return value

    model_config = SettingsConfigDict(
        env_file=BASE_DIR.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()
