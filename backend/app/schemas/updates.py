from pydantic import BaseModel

from app.schemas.types import UtcDateTime


class UpdateChange(BaseModel):
    sha: str
    title: str
    date: str | None = None


class UpdaterRun(BaseModel):
    running: bool = False
    started_at: str | None = None
    finished_at: str | None = None
    # "ok" or "failed" for the last run that ended; null before any
    result: str | None = None
    # the end of what the last run printed, for when it failed
    log: str | None = None


class UpdateStatus(BaseModel):
    # the commit this backend runs, and the newest published one; null when unknown
    current: str | None
    latest: str | None
    available: bool
    behind: int | None
    changes: list[UpdateChange]
    checked_at: UtcDateTime | None
    error: str | None
    # whether the button can do anything: the updater is set up and this
    # backend knows its own version
    can_update: bool
    updater: UpdaterRun | None
