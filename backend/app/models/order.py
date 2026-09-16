import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class OrderSource(str, enum.Enum):
    ALLEGRO = "ALLEGRO"
    ERLI = "ERLI"


class OrderStatus(str, enum.Enum):
    NEW = "NEW"
    CONFIRMED = "CONFIRMED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


# one shared type object, referenced by both the orders table and the history
# table: on PostgreSQL an Enum is a real database type, so declaring it twice
# would try to CREATE TYPE order_status twice
ORDER_STATUS = Enum(OrderStatus, name="order_status")


class Order(Base):
    __tablename__ = "orders"

    # a marketplace's order number is unique only within that marketplace,
    # and re-importing must not duplicate an order already stored
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_orders_source_external_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    external_id: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )

    source: Mapped[OrderSource] = mapped_column(
        Enum(OrderSource, name="order_source"),
        nullable=False,
    )

    status: Mapped[OrderStatus] = mapped_column(
        ORDER_STATUS,
        default=OrderStatus.NEW,
        nullable=False,
    )

    customer_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        default="PLN",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    status_history: Mapped[list["OrderStatusHistory"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderStatusHistory.changed_at",
    )


class OrderStatusHistory(Base):
    """Append-only record of status transitions for one order."""

    __tablename__ = "order_status_history"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    from_status: Mapped[OrderStatus] = mapped_column(ORDER_STATUS, nullable=False)
    to_status: Mapped[OrderStatus] = mapped_column(ORDER_STATUS, nullable=False)

    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    order: Mapped["Order"] = relationship(back_populates="status_history")
