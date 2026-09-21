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

    # who the token belongs to, as the marketplace names them; read once when
    # the account is connected, purely so Settings can say which account it is
    account_login: Mapped[str | None] = mapped_column(String(255), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class IntegrationSettings(Base):
    """A marketplace application's own credentials, entered in Settings.

    The client id and secret identify the application registered on the
    marketplace's developer portal, as opposed to IntegrationCredential, which
    holds the token a seller granted it. When a row exists it is used instead
    of the environment variables of the same meaning; without one the
    environment applies, as before. The secret is stored as plain text, the
    same exposure as the refresh token beside it and as `.env`, and is never
    returned by the API.
    """

    __tablename__ = "integration_settings"

    provider: Mapped[str] = mapped_column(String(50), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    client_secret: Mapped[str] = mapped_column(Text, nullable=False)
    # the User-Agent generated for the application on the developer portal
    user_agent: Mapped[str] = mapped_column(String(255), nullable=False)
    # "sandbox" or "production": which of the marketplace's two worlds the
    # application is registered in, and so which URLs it talks to
    environment: Mapped[str] = mapped_column(String(20), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
