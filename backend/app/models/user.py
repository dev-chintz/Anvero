from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user_permission import UserPermission

# a plain string, not a database enum type: only two values today, but a
# native Postgres enum needs its own migration to add a third, and `role`
# follows the same reasoning `payment_type` does (DATABASE.md)
ADMIN_ROLE = "admin"
USER_ROLE = "user"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # "admin" can do everything; "user" is limited to the areas and levels
    # granted through `permissions` below. Existing accounts were migrated to
    # "admin" so nobody already using the application lost access.
    role: Mapped[str] = mapped_column(
        String(10),
        default=USER_ROLE,
        server_default=USER_ROLE,
        nullable=False,
    )

    # Carried in every login token and compared on every request: raising it
    # (a new password) makes every token issued before worthless, where they
    # would otherwise live out their eight hours (DATABASE.md).
    token_version: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    permissions: Mapped[list["UserPermission"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
