import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.user import User  # noqa: F401 -- resolves the "User" relationship


class OrderSource(str, enum.Enum):
    ALLEGRO = "ALLEGRO"
    ERLI = "ERLI"


class OrderStatus(str, enum.Enum):
    NEW = "NEW"
    CONFIRMED = "CONFIRMED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class PaymentType(str, enum.Enum):
    """How the buyer pays, in marketplace-neutral terms.

    Each adapter translates its marketplace's own values into these.
    """

    ONLINE = "ONLINE"
    BANK_TRANSFER = "BANK_TRANSFER"
    CASH_ON_DELIVERY = "CASH_ON_DELIVERY"
    # paid after delivery on agreed terms, e.g. Allegro's deferred payment
    DEFERRED = "DEFERRED"
    OTHER = "OTHER"


class AddressType(str, enum.Enum):
    DELIVERY = "DELIVERY"
    INVOICE = "INVOICE"
    PICKUP_POINT = "PICKUP_POINT"


# one shared type object, referenced by both the orders table and the history
# table: on PostgreSQL an Enum is a real database type, so declaring it twice
# would try to CREATE TYPE order_status twice
ORDER_STATUS = Enum(OrderStatus, name="order_status")

# Stored as plain strings rather than database enum types: these lists grow
# with every marketplace added, and on PostgreSQL a new value in a real enum
# type needs its own migration.
PAYMENT_TYPE = Enum(PaymentType, native_enum=False, length=32)
ADDRESS_TYPE = Enum(AddressType, native_enum=False, length=32)


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

    # When the buyer placed the order. For an imported order that is the
    # marketplace's purchase time, which can be long before the import that
    # created the row, so date filters, sorting and "this week" use this.
    ordered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        nullable=False,
    )

    # When the row was created in Anvero.
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

    # Set when an import finds the order cancelled on the marketplace. The
    # Anvero status is the operator's and is not overwritten, so this is what
    # tells them; the warning stands until they set the status to CANCELLED.
    marketplace_cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Order details. Every one is optional: an order entered by hand may have
    # none, and a marketplace may leave any of them out. For an imported order
    # the marketplace owns all of them, and a re-import replaces them.

    # the buyer; the email above predates these and stays required
    customer_login: Mapped[str | None] = mapped_column(String(255))
    customer_first_name: Mapped[str | None] = mapped_column(String(255))
    customer_last_name: Mapped[str | None] = mapped_column(String(255))
    customer_company_name: Mapped[str | None] = mapped_column(String(255))
    customer_phone: Mapped[str | None] = mapped_column(String(64))

    # what the buyer wrote to the seller at checkout
    buyer_message: Mapped[str | None] = mapped_column(Text)

    delivery_method: Mapped[str | None] = mapped_column(String(255))
    delivery_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    pickup_point_id: Mapped[str | None] = mapped_column(String(255))
    pickup_point_name: Mapped[str | None] = mapped_column(String(255))

    payment_type: Mapped[PaymentType | None] = mapped_column(PAYMENT_TYPE)
    # the operator behind the payment, as the marketplace names it
    payment_provider: Mapped[str | None] = mapped_column(String(64))
    # null means unknown; zero means known to be unpaid
    paid_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    invoice_required: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )

    status_history: Mapped[list["OrderStatusHistory"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderStatusHistory.changed_at",
    )

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderItem.position",
    )

    addresses: Mapped[list["OrderAddress"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )

    def address(self, address_type: AddressType) -> "OrderAddress | None":
        return next((a for a in self.addresses if a.type is address_type), None)


class OrderItem(Base):
    """One line of an order: a product, how many, and at what unit price."""

    __tablename__ = "order_items"

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

    # keeps the marketplace's line order; ids carry no order of their own
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # the marketplace's id for this line
    external_id: Mapped[str | None] = mapped_column(String(255))
    # the marketplace's id for the listing the item was bought from
    offer_id: Mapped[str | None] = mapped_column(String(255))
    # the seller's own product code, when the listing carries one
    sku: Mapped[str | None] = mapped_column(String(255))

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    # per unit, in the order's currency
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")


class OrderAddress(Base):
    """A delivery, invoice or pickup point address; at most one of each."""

    __tablename__ = "order_addresses"

    __table_args__ = (
        UniqueConstraint("order_id", "type", name="uq_order_addresses_order_id_type"),
    )

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

    type: Mapped[AddressType] = mapped_column(ADDRESS_TYPE, nullable=False)

    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    company_name: Mapped[str | None] = mapped_column(String(255))
    street: Mapped[str | None] = mapped_column(String(255))
    postal_code: Mapped[str | None] = mapped_column(String(32))
    city: Mapped[str | None] = mapped_column(String(255))
    country_code: Mapped[str | None] = mapped_column(String(8))
    phone: Mapped[str | None] = mapped_column(String(64))
    # company tax number, on invoice addresses
    tax_id: Mapped[str | None] = mapped_column(String(64))

    order: Mapped["Order"] = relationship(back_populates="addresses")


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

    # Who made the change. Null for entries recorded before logins existed, and
    # if the account is later deleted: the history must outlive the user.
    changed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    order: Mapped["Order"] = relationship(back_populates="status_history")
    changed_by: Mapped["User | None"] = relationship()

    @property
    def changed_by_email(self) -> str | None:
        return self.changed_by.email if self.changed_by is not None else None
