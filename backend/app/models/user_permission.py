import enum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class PermissionArea(str, enum.Enum):
    """Where the interface groups actions for a permission (settings.md, "Users").

    Grouped, not one per endpoint: a business owner grants access by the part
    of the application someone works in, not by individual API calls.
    """

    ORDERS = "orders"
    MESSAGES = "messages"
    AFTER_SALES = "after_sales"
    LABELS = "labels"
    FINANCE = "finance"
    INTEGRATIONS = "integrations"


class PermissionLevel(str, enum.Enum):
    VIEW = "view"
    MANAGE = "manage"


class UserPermission(Base):
    __tablename__ = "user_permissions"
    __table_args__ = (UniqueConstraint("user_id", "area", name="uq_user_permissions_user_area"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # plain strings, not a database enum type, like `role`: the list of areas
    # grows as the application does, and a native enum needs its own
    # migration for every new value (DATABASE.md, "payment_type")
    area: Mapped[str] = mapped_column(String(20), nullable=False)
    level: Mapped[str] = mapped_column(String(10), nullable=False)

    user: Mapped["User"] = relationship(back_populates="permissions")
