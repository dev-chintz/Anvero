import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field

from app.core.order_number import format_order_number
from app.models.order import (
    AddressType,
    Order,
    OrderSource,
    OrderStatus,
    PaymentType,
)
from app.schemas.types import UtcDateTime

BUYER_MESSAGE_MAX_LENGTH = 4000
SELLER_NOTE_MAX_LENGTH = 4000


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


class OrderUpdate(BaseModel):
    status: OrderStatus


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
    # already flat columns on `orders`, so free to add to the list response:
    # no join, unlike items, which is why those are not here too
    customer_login: str | None = None
    customer_first_name: str | None = None
    customer_last_name: str | None = None
    payment_type: PaymentType | None = None
    payment_provider: str | None = None
    # the list sorts and flags orders by it
    dispatch_by: UtcDateTime | None = None
    # small, and the list shows them in its Shipping column
    shipments: list[ShipmentRead] = Field(default_factory=list)

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
        )


def _address(order: Order, address_type: AddressType) -> Address | None:
    row = order.address(address_type)
    return Address.model_validate(row) if row is not None else None


# kept as an alias to match the requested naming in the task spec
OrderResponse = OrderRead


class OrderListResponse(BaseModel):
    items: list[OrderRead]
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
