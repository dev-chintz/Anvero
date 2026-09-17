import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.order import (
    AddressType,
    Order,
    OrderSource,
    OrderStatus,
    PaymentType,
)
from app.schemas.types import UtcDateTime

BUYER_MESSAGE_MAX_LENGTH = 4000


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


class OrderItemRead(OrderItemCreate):
    id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


class OrderDetailRead(OrderRead, OrderDetails):
    """A single order with its details; the list returns OrderRead only."""

    items: list[OrderItemRead] = Field(default_factory=list)

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


class OrderStats(BaseModel):
    total_orders: int
    total_revenue: Decimal
    this_week: int
    pending: int
    cancellation_warnings: int
    by_status: dict[str, int]
    by_source: dict[str, int]
