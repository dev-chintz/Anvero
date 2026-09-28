import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.user import User


class AppUpdate(Base):
    """One change of the version the backend runs: the history on Settings, Updates.

    Started from Settings, a row is written when the button is pressed and closed
    by the new backend on its first start, since the one that wrote it is
    replaced on the way. A version that arrived any other way (by hand over SSH,
    a first start) is written by the backend that finds itself on it, already
    closed, with no one who started it.
    """

    __tablename__ = "app_updates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # the full commits, as `APP_COMMIT` and GitHub give them; from is null for a first start
    from_commit: Mapped[str | None] = mapped_column(String(40))
    to_commit: Mapped[str] = mapped_column(String(40), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    started_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # null while under way; then "ok" or "failed"
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[str | None] = mapped_column(String(16))
    # "settings" for the button, "outside" for a version found on start
    via: Mapped[str] = mapped_column(String(16), nullable=False)
    # why it failed, in a line or the end of the updater's log
    detail: Mapped[str | None] = mapped_column(String(4000))

    started_by: Mapped[User | None] = relationship(lazy="joined")

    @property
    def started_by_email(self) -> str | None:
        return self.started_by.email if self.started_by else None
