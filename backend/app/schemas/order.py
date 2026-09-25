import uuid
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    computed_field,
    model_validator,
)

from app.core.order_number import format_order_number
from app.models.order import (
    AddressType,
    Order,
    OrderSource,
    OrderStatus,
    PaymentType,
)
from app.schemas.marketplace_write import MarketplaceWriteRead
from app.schemas.types import UtcDateTime

BUYER_MESSAGE_MAX_LENGTH = 4000
SELLER_NOTE_MAX_LENGTH = 4000
INTERNAL_NOTE_MAX_LENGTH = 4000


def _text(max_length: int):
    # min_length 1: an absent value is null, never an empty string, so the
    # interface has one case to handle rather than two
    return Field(default=None, min_length=1, max_length=max_length)


def _amount():
    return Field(default=None, ge=0, max_digits=12, decimal_places=2)


class OrderBase(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    source: OrderSource
    customer_email: EmailStr
    total_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="PLN", min_length=3, max_length=3)


class Address(BaseModel):
    first_name: str | None = _text(255)
    last_name: str | None = _text(255)
    company_name: str | None = _text(255)
    street: str | None = _text(255)
    postal_code: str | None = _text(32)
    city: str | None = _text(255)
    country_code: str | None = _text(8)
    phone: str | None = _text(64)
    # company tax number, on invoice addresses
    tax_id: str | None = _text(64)

    model_config = ConfigDict(from_attributes=True)


class Customer(BaseModel):
    """The buyer, beyond the email every order already carries."""

    login: str | None = _text(255)
    first_name: str | None = _text(255)
    last_name: str | None = _text(255)
    company_name: str | None = _text(255)
    phone: str | None = _text(64)


class OrderItemCreate(BaseModel):
    external_id: str | None = _text(255)
    offer_id: str | None = _text(255)
    sku: str | None = _text(255)
    name: str = Field(min_length=1, max_length=500)
    quantity: int = Field(gt=0)
    # per unit, in the order's currency; zero allows a free item
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    # the offer's picture, fetched from Allegro at import time; best effort,
    # so a deleted offer or a missing scope leaves this null
    image_url: str | None = _text(500)


class OrderItemRead(OrderItemCreate):
    id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)


class ShipmentCreate(BaseModel):
    external_id: str | None = _text(255)
    carrier_id: str | None = _text(64)
    carrier_name: str | None = _text(255)
    waybill: str = Field(min_length=1, max_length=255)
    shipped_at: UtcDateTime | None = None
    # the carrier's latest tracking status code and when it reported it; null
    # when nothing has been read
    tracking_status: str | None = _text(32)
    tracking_updated_at: UtcDateTime | None = None


class ShipmentRead(ShipmentCreate):
    id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)


class BillingEntryCreate(BaseModel):
    source: OrderSource
    external_id: str = Field(min_length=1, max_length=255)
    occurred_at: UtcDateTime
    type_id: str = Field(min_length=1, max_length=32)
    type_name: str | None = _text(255)
    # signed: a charge is negative, a refund or credit positive
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)
    order_external_id: str | None = _text(255)
    offer_id: str | None = _text(255)
    offer_name: str | None = _text(500)


class BillingEntryRead(BaseModel):
    id: uuid.UUID
    occurred_at: UtcDateTime
    type_id: str
    type_name: str | None
    amount: Decimal
    currency: str

    model_config = ConfigDict(from_attributes=True)


class OrderBillingRead(BaseModel):
    """What the marketplace has charged, and credited back, for one order."""

    entries: list[BillingEntryRead]
    # the entries added up, in the order's currency: negative is a net charge
    total: Decimal
    currency: str


class PickupPoint(BaseModel):
    id: str | None = _text(255)
    name: str | None = _text(255)
    address: Address | None = None


class Delivery(BaseModel):
    method: str | None = _text(255)
    cost: Decimal | None = _amount()
    address: Address | None = None
    pickup_point: PickupPoint | None = None


class Payment(BaseModel):
    type: PaymentType | None = None
    provider: str | None = _text(64)
    # null means unknown; zero means known to be unpaid
    paid_amount: Decimal | None = _amount()
    paid_at: UtcDateTime | None = None


class Invoice(BaseModel):
    required: bool = False
    address: Address | None = None


class OrderDetails(BaseModel):
    """Everything about an order beyond its identity, status and total.

    All of it is optional: a hand-entered order may have none, and a
    marketplace may leave any part out.
    """

    customer: Customer = Field(default_factory=Customer)
    items: list[OrderItemCreate] = Field(default_factory=list)
    delivery: Delivery = Field(default_factory=Delivery)
    payment: Payment = Field(default_factory=Payment)
    invoice: Invoice = Field(default_factory=Invoice)
    buyer_message: str | None = _text(BUYER_MESSAGE_MAX_LENGTH)
    # the seller's own note on the order, e.g. Allegro's "note" on the
    # checkout form; written by the seller, not the buyer, and read-only
    # here - a re-import refreshes it like every other detail
    seller_note: str | None = _text(SELLER_NOTE_MAX_LENGTH)
    # the latest moment the seller must hand the parcel over, as the
    # marketplace states it; null when it states none
    dispatch_by: UtcDateTime | None = None
    # the parcels sent; None means "not known", which an import leaves the
    # stored ones alone for, unlike an empty list, which says there are none
    shipments: list[ShipmentCreate] | None = None


class OrderCreate(OrderBase, OrderDetails):
    status: OrderStatus = OrderStatus.NEW
    # the marketplace's own status, unmapped; None for a hand-made order
    marketplace_status_label: str | None = _text(64)
    # when the buyer placed the order; omitted means "now". A value without a
    # zone is taken as UTC.
    ordered_at: UtcDateTime | None = None
    # when the marketplace last changed the order, by its own clock; compared
    # with when the operator last set the status, never stored
    marketplace_updated_at: UtcDateTime | None = None


class OrderUpdate(BaseModel):
    status: OrderStatus


class OrderNoteUpdate(BaseModel):
    """The operator's own note on an order; null, or only spaces, takes it away."""

    note: str | None = Field(default=None, max_length=INTERNAL_NOTE_MAX_LENGTH)

    @model_validator(mode="after")
    def _blank_is_no_note(self) -> "OrderNoteUpdate":
        if self.note is not None and not self.note.strip():
            self.note = None
        return self


class OrderMarksUpdate(BaseModel):
    """The operator's marks on an order; one left out stays as it is."""

    starred: bool | None = None
    flagged: bool | None = None


class OrderRead(OrderBase):
    id: uuid.UUID
    # Anvero's own number, continuous across sources and never reused
    order_number: int
    status: OrderStatus
    ordered_at: UtcDateTime
    created_at: UtcDateTime
    updated_at: UtcDateTime
    # what the marketplace's status mapped to at the last import; the
    # interface shows it when it differs from `status`
    marketplace_status: OrderStatus | None = None
    # the same status in the marketplace's own words, which keep a distinction
    # Anvero's five statuses do not, e.g. Allegro's READY_FOR_SHIPMENT
    marketplace_status_label: str | None = None
    marketplace_cancelled_at: UtcDateTime | None = None
    # already flat columns on `orders`, so free to add to any response
    customer_login: str | None = None
    customer_first_name: str | None = None
    customer_last_name: str | None = None
    payment_type: PaymentType | None = None
    payment_provider: str | None = None
    # the list sorts and flags orders by it
    dispatch_by: UtcDateTime | None = None
    # small, and the list shows them in its Shipping column
    shipments: list[ShipmentRead] = Field(default_factory=list)
    # when the status last changed; null for an order that has kept the one it
    # was placed with (the list then counts from `ordered_at`)
    status_changed_at: UtcDateTime | None = None
    # the operator's own marks, for finding an order again
    starred: bool = False
    flagged: bool = False
    # the list's small facts: where it goes (delivery country, e.g. PL), how much
    # has been paid (null when unknown), whether an invoice is wanted, and whether
    # the buyer left a message or the seller a note
    delivery_country_code: str | None = None
    paid_amount: Decimal | None = None
    invoice_required: bool = False
    has_buyer_message: bool = False
    has_seller_note: bool = False
    # set while an operator has deleted the order; such an order is in no list
    # unless it was asked for, and is kept to be restored
    deleted_at: UtcDateTime | None = None
    deleted_by: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def order_label(self) -> str:
        """The number as it is shown and searched, e.g. AN-000123."""
        return format_order_number(self.order_number)


class OrderDetailRead(OrderRead, OrderDetails):
    """A single order with its details; the list returns OrderRead only."""

    items: list[OrderItemRead] = Field(default_factory=list)
    shipments: list[ShipmentRead] = Field(default_factory=list)
    # the operator's own note, written in Anvero; not in the list, and no marketplace has it
    internal_note: str | None = None

    @classmethod
    def from_order(cls, order: Order) -> "OrderDetailRead":
        """Gather the flat detail columns and child rows into nested objects."""
        base = OrderRead.model_validate(order)
        has_pickup_point = (
            order.pickup_point_id
            or order.pickup_point_name
            or order.address(AddressType.PICKUP_POINT) is not None
        )
        return cls(
            **base.model_dump(),
            customer=Customer(
                login=order.customer_login,
                first_name=order.customer_first_name,
                last_name=order.customer_last_name,
                company_name=order.customer_company_name,
                phone=order.customer_phone,
            ),
            items=[OrderItemRead.model_validate(item) for item in order.items],
            delivery=Delivery(
                method=order.delivery_method,
                cost=order.delivery_cost,
                address=_address(order, AddressType.DELIVERY),
                pickup_point=(
                    PickupPoint(
                        id=order.pickup_point_id,
                        name=order.pickup_point_name,
                        address=_address(order, AddressType.PICKUP_POINT),
                    )
                    if has_pickup_point
                    else None
                ),
            ),
            payment=Payment(
                type=order.payment_type,
                provider=order.payment_provider,
                paid_amount=order.paid_amount,
                paid_at=order.paid_at,
            ),
            invoice=Invoice(
                required=order.invoice_required,
                address=_address(order, AddressType.INVOICE),
            ),
            buyer_message=order.buyer_message,
            seller_note=order.seller_note,
            internal_note=order.internal_note,
        )


class OrderChangeResult(OrderDetailRead):
    """An order after a change made in Anvero, and what became of sending it.

    `marketplace_write` is null when nothing was for the marketplace (an Erli
    order, a status Allegro is not told); otherwise it says whether the change
    was sent, held back by safe mode, or refused, and why.
    """

    marketplace_write: MarketplaceWriteRead | None = None


class ShipmentAdd(BaseModel):
    """A tracking number typed in on an order."""

    # Allegro's carrier id, e.g. INPOST; OTHER needs carrier_name
    carrier_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z_]+$")
    carrier_name: str | None = _text(255)
    waybill: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def _other_needs_a_name(self) -> "ShipmentAdd":
        if self.carrier_id == "OTHER" and not self.carrier_name:
            raise ValueError("carrier_name is required when carrier_id is OTHER")
        return self


def _address(order: Order, address_type: AddressType) -> Address | None:
    row = order.address(address_type)
    return Address.model_validate(row) if row is not None else None


# kept as an alias to match the requested naming in the task spec
OrderResponse = OrderRead


class OrderItemSummary(BaseModel):
    """What the list shows of one item: enough to recognise the product."""

    name: str
    sku: str | None = None
    quantity: int
    image_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class OrderListItem(OrderRead):
    """An order as `GET /orders` lists it: the list's fields and its items in short."""

    items: list[OrderItemSummary] = Field(default_factory=list)


class OrderListResponse(BaseModel):
    items: list[OrderListItem]
    total: int
    skip: int
    limit: int


class OrderStatusHistoryRead(BaseModel):
    id: uuid.UUID
    from_status: OrderStatus
    to_status: OrderStatus
    changed_at: UtcDateTime
    # email of the user who made the change; null for changes recorded before
    # logins existed, or whose account has since been deleted
    changed_by: str | None = Field(default=None, validation_alias="changed_by_email")

    model_config = ConfigDict(from_attributes=True)


class ProductionOrder(BaseModel):
    """One order that needs some of a production line's product."""

    id: uuid.UUID
    order_label: str
    source: OrderSource
    status: OrderStatus
    # how many of the line's product this order takes
    quantity: int
    dispatch_by: UtcDateTime | None


class ProductionLine(BaseModel):
    """One product to make, with everything the waiting orders need of it."""

    # what the line is grouped by: "sku:...", "offer:..." or "name:..."
    key: str
    sku: str | None
    offer_id: str | None
    name: str
    image_url: str | None
    quantity: int
    # the earliest dispatch deadline among its orders
    dispatch_by: UtcDateTime | None
    orders: list[ProductionOrder]


class ProductionList(BaseModel):
    lines: list[ProductionLine]
    # orders in the to-make queue, including any without items
    order_count: int


class OrderQueueCounts(BaseModel):
    """How many orders wait in each work queue; see OrderQueue."""

    to_make: int
    unpaid: int
    to_ship: int
    late: int


class OrderStats(BaseModel):
    total_orders: int
    total_revenue: Decimal
    this_week: int
    pending: int
    cancellation_warnings: int
    queues: OrderQueueCounts
    by_status: dict[str, int]
    by_source: dict[str, int]
