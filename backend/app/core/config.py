from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

# values shipped in examples or typed in a hurry; a token signed with any of
# these can be forged by anyone who has read this repository
_PLACEHOLDER_SECRET_KEYS = {"", "change_me", "changeme", "secret", "secret_key"}
MIN_SECRET_KEY_LENGTH = 32


def ensure_secret_key(value: str) -> None:
    """Refuse to run the API with a signing key an attacker could guess.

    Checked when the API starts rather than when settings load, so migrations
    and scripts that never sign a token keep working on a fresh machine.
    """
    if value.strip().lower() in _PLACEHOLDER_SECRET_KEYS or len(value) < MIN_SECRET_KEY_LENGTH:
        raise RuntimeError(
            "SECRET_KEY is missing, a placeholder, or shorter than "
            f"{MIN_SECRET_KEY_LENGTH} characters. Anyone knowing it can sign a "
            "valid login token. Run scripts\\bootstrap.ps1, which generates one, "
            "or set a long random value in backend/.env."
        )


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

    # a working day: one login per day, and a stolen token is dead by evening.
    # There is no revocation, so longer means a leaked token lives longer.
    access_token_expire_minutes: int = Field(default=480, gt=0)

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
