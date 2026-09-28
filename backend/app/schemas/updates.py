import uuid

from pydantic import BaseModel, Field

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


class UpdateHistoryEntry(BaseModel):
    """One change of the running version, newest first in `UpdateStatus.history`."""

    id: uuid.UUID
    # short commits; from is null for the first version this database saw
    from_commit: str | None
    to_commit: str
    started_at: UtcDateTime
    # null while the update is under way
    finished_at: UtcDateTime | None
    # "ok" or "failed"; null while under way
    result: str | None
    # "settings" for the button, "outside" for a version reached another way
    via: str
    # the e-mail of the administrator who pressed the button; null otherwise
    started_by: str | None
    # why it failed
    detail: str | None


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
    history: list[UpdateHistoryEntry] = Field(default_factory=list)
