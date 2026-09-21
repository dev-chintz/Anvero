from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IntegrationCredential(Base):
    """The latest refresh token issued by a marketplace.

    Allegro rotates refresh tokens: every refresh returns a new one and the
    previous one stops working 60 seconds later. The token configured in the
    environment is therefore only a starting point, and the rotated token has
    to be kept somewhere the next run can find it.
    """

    __tablename__ = "integration_credentials"

    provider: Mapped[str] = mapped_column(String(50), primary_key=True)

    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)

    # SHA-256 of the environment token this chain of rotations started from.
    # When the environment holds a different token, someone authorized the
    # application again, and the stored chain is stale.
    seed_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    # when the last import that fetched everything it set out to finished
    # (minus a small overlap); the next one asks only for orders changed
    # since. Null until one has, and again after re-authorization, since a
    # different seller account has a different order history.
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
