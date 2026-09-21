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
    event,
    false,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.user import User


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
        UniqueConstraint("order_number", name="uq_orders_order_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Anvero's own number for the order, continuous across every source and
    # given once, when the row is created (see next_order_number): it is never
    # changed and never reused. The prefix and padding it is shown with live in
    # app/core/order_number.py.
    order_number: Mapped[int] = mapped_column(Integer, nullable=False)

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

    # What the marketplace's own status mapped to at the last import, kept
    # beside the Anvero status rather than replacing it: the operator owns
    # theirs, but needs to see when the marketplace has moved on. NULL for an
    # order no import has touched.
    marketplace_status: Mapped[OrderStatus | None] = mapped_column(
        ORDER_STATUS,
        nullable=True,
    )

    # The same status in the marketplace's own words, unmapped: Anvero's five
    # statuses collapse distinctions the operator can see in the marketplace's
    # panel, e.g. Allegro's PROCESSING and READY_FOR_SHIPMENT are both
    # CONFIRMED here.
    marketplace_status_label: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    # Set when an import finds the order cancelled on the marketplace, and
    # kept: the import sets the status to CANCELLED, so this is what stays
    # visible if the operator later moves it back to an active one.
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
    # the seller's own note on the order, written on the marketplace itself
    # (e.g. Allegro's checkout-form "note"); read-only here
    seller_note: Mapped[str | None] = mapped_column(Text)

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

    # loaded together with the order (one extra query per page, not one per
    # row), since the list shows the carrier and waybill in its own column
    shipments: Mapped[list["OrderShipment"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderShipment.position",
        lazy="selectin",
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
    # the offer's own picture, fetched from Allegro at import time; best
    # effort, so a deleted offer or a missing scope leaves this null rather
    # than failing the import
    image_url: Mapped[str | None] = mapped_column(String(500))

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    # per unit, in the order's currency
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")


class OrderShipment(Base):
    """A parcel sent for an order: which carrier, under which waybill.

    Owned by the marketplace like the items are: an import replaces them.
    """

    __tablename__ = "order_shipments"

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

    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # the marketplace's id for the shipment
    external_id: Mapped[str | None] = mapped_column(String(255))
    # the carrier as the marketplace names it, e.g. DHL, or OTHER with a name
    carrier_id: Mapped[str | None] = mapped_column(String(64))
    carrier_name: Mapped[str | None] = mapped_column(String(255))
    waybill: Mapped[str] = mapped_column(String(255), nullable=False)
    # when the seller added the tracking number, by the marketplace's clock
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # where the carrier says the parcel is: the code of its latest tracking
    # status (IN_TRANSIT, DELIVERED, ...) and when the carrier last reported.
    # Null when nothing has been read, e.g. a carrier Allegro cannot track.
    tracking_status: Mapped[str | None] = mapped_column(String(32))
    tracking_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    order: Mapped["Order"] = relationship(back_populates="shipments")


class BillingEntry(Base):
    """One operation on the seller's account with the marketplace: a fee, a
    correction, a refund of a fee.

    Kept by the marketplace's own id and never changed once stored, so a
    re-read only adds what is new. Not tied to an order by a foreign key: the
    entry names the marketplace's order id, and may be read before the order
    itself is, or belong to none (a subscription, an advertising fee).
    """

    __tablename__ = "billing_entries"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_billing_entries_source_external_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    source: Mapped[OrderSource] = mapped_column(
        Enum(OrderSource, native_enum=False, length=32), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # the marketplace's short code and name for the kind of operation
    type_id: Mapped[str] = mapped_column(String(32), nullable=False)
    type_name: Mapped[str | None] = mapped_column(String(255))

    # signed: a charge is negative, a refund or credit positive
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    # the marketplace's id of the order it concerns, for the types that name one
    order_external_id: Mapped[str | None] = mapped_column(String(255), index=True)
    offer_id: Mapped[str | None] = mapped_column(String(255))
    offer_name: Mapped[str | None] = mapped_column(String(500))


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


class Counter(Base):
    """A named counter that hands out numbers in sequence."""

    __tablename__ = "counters"

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False)


ORDER_NUMBER_COUNTER = "order_number"


def next_order_number(connection) -> int:
    """Take the next order number, inside the caller's transaction.

    The counter row is updated before it is read, so on PostgreSQL the update
    holds the row lock until the transaction ends: two orders created at once
    cannot read the same value, and a rolled-back insert gives its number back
    only if nothing else took one meanwhile (so gaps are possible, repeats are
    not). A plain autoincrement column cannot do this, since it is only
    allowed on the primary key, which here is a UUID. The row is normally made
    by the migration; a database built straight from the models starts it here.
    """
    where = Counter.name == ORDER_NUMBER_COUNTER
    result = connection.execute(update(Counter).where(where).values(value=Counter.value + 1))
    if result.rowcount == 0:
        connection.execute(insert(Counter).values(name=ORDER_NUMBER_COUNTER, value=1))
        return 1
    return connection.execute(select(Counter.value).where(where)).scalar_one()


@event.listens_for(Order, "before_insert")
def _number_a_new_order(mapper, connection, order: Order) -> None:
    # every path that creates an order - the API, an import, a script - goes
    # through the ORM, so numbering it here covers them all
    if order.order_number is None:
        order.order_number = next_order_number(connection)
