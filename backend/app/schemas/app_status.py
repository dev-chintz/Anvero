from typing import Literal

from pydantic import BaseModel

from app.schemas.types import UtcDateTime

# "off": not set up at all; "ok"; "warning": works, but needs attention soon;
# "error": does not work until someone acts
HealthState = Literal["off", "ok", "warning", "error"]


class ScheduleStatus(BaseModel):
    """This backend's own import schedule; another backend's is invisible."""

    interval_minutes: int
    running: bool
    started_at: UtcDateTime | None = None
    next_run_at: UtcDateTime | None = None
    last_run_at: UtcDateTime | None = None


class LastImport(BaseModel):
    """How the last import ended, whoever ran it; null fields before the first."""

    at: UtcDateTime | None = None
    created: int | None = None
    updated: int | None = None
    error: str | None = None


class AllegroHealth(BaseModel):
    state: HealthState
    # what makes the state less than "ok", as codes the interface words
    problems: list[str]
    application_complete: bool
    connected: bool
    environment: Literal["sandbox", "production"]
    account_login: str | None
    # when Allegro issued the stored refresh token, and when it lapses unless
    # an import uses it first; null while no token is stored in the database
    token_issued_at: UtcDateTime | None
    token_expires_at: UtcDateTime | None
    last_import: LastImport
    schedule: ScheduleStatus


class ErliHealth(BaseModel):
    state: HealthState
    problems: list[str]
    # an API key is set; Erli's key does not expire
    configured: bool
    last_import: LastImport
    # there is no schedule for Erli yet: imports run from the script only
    schedule: ScheduleStatus | None


class AppStatus(BaseModel):
    checked_at: UtcDateTime
    version: str
    safe_mode: bool
    allegro: AllegroHealth
    erli: ErliHealth
