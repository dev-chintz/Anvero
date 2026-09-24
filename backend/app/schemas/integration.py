from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AllegroStatus(BaseModel):
    """What Settings shows about the Allegro connection. Carries no secret."""

    # ready to import: the application's credentials and a token are both there
    configured: bool
    # a seller account has been connected (a token exists)
    connected: bool
    # client id, client secret and User-Agent are all set
    application_complete: bool
    client_id: str | None
    user_agent: str | None
    environment: Literal["sandbox", "production"]
    # "settings" (entered in Settings) or "environment" (backend/.env)
    source: Literal["settings", "environment"]
    # the connected seller's login; null when unknown or not connected
    account_login: str | None
    # how the last import ended, whether started by the button or the schedule;
    # all null before the first one
    last_import_at: datetime | None = None
    last_import_created: int | None = None
    last_import_updated: int | None = None
    # set when the last import failed
    last_import_error: str | None = None
    # minutes between imports the backend runs by itself; 0 means it does not
    auto_import_interval_minutes: int = 0


class AllegroSettingsRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=255)
    # blank or absent keeps the secret already stored
    client_secret: str | None = Field(default=None, max_length=1000)
    user_agent: str = Field(min_length=1, max_length=255)
    environment: Literal["sandbox", "production"]


class AllegroConnectStart(BaseModel):
    flow_id: str
    # the page the seller opens, logged in to Allegro, to confirm
    verification_uri: str
    user_code: str
    # seconds to wait between polls, and how long the code lives
    interval: int
    expires_in: int


class AllegroConnectPoll(BaseModel):
    status: Literal["pending", "connected"]
    account_login: str | None = None


class AllegroImportResult(BaseModel):
    created: int
    updated: int
    cancellation_warnings: int

    model_config = ConfigDict(from_attributes=True)


class ErliStatus(BaseModel):
    """What Settings shows about Erli. Carries no key, only its last characters."""

    # a key is set, in Settings or in the environment
    configured: bool
    # "settings" (entered in Settings), "environment" (backend/.env) or "none"
    source: Literal["settings", "environment", "none"]
    # the key's last characters, to tell one key from another; null with none
    key_hint: str | None = None
    # how the last import ended, whether by the button or the script; all null
    # before the first one
    last_import_at: datetime | None = None
    last_import_created: int | None = None
    last_import_updated: int | None = None
    # set when the last import failed
    last_import_error: str | None = None


class ErliSettingsRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=500)

    @field_validator("api_key")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        # a key pasted from the panel often carries a trailing newline or space
        value = value.strip()
        if not value:
            raise ValueError("The API key is empty")
        return value
