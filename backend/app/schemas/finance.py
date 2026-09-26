"""The Finance page: a period's sales and fees, per order and per product."""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.models.order import OrderSource
from app.schemas.types import UtcDateTime


class SourceMoney(BaseModel):
    source: OrderSource
    sales: Decimal
    orders: int
    fees: Decimal
    # the fees in the period before, for the comparison
    previous_sales: Decimal
    previous_fees: Decimal
    # sent to the bank in the period; null for a marketplace whose payouts are not read
    paid_out: Decimal | None = None


class FeeTypeMoney(BaseModel):
    source: OrderSource
    type_id: str
    type_name: str | None
    # positive: what the marketplace took; a refund of a fee lowers it
    fees: Decimal
    previous_fees: Decimal


class Settlement(BaseModel):
    """What a marketplace took out of the proceeds to pay its fees, beside the fees
    booked in the same period; what is still unsettled over everything read, since
    when; and when its fees were last read."""

    source: OrderSource
    fees: Decimal
    settled: Decimal
    # fees not yet taken from the proceeds, over all entries held; 0 when all are
    unsettled: Decimal
    held_since: UtcDateTime | None
    synced_at: UtcDateTime | None


class FinanceSummary(BaseModel):
    date_from: date
    date_to: date
    previous_from: date
    previous_to: date
    currency: str
    sales: Decimal
    orders: int
    fees: Decimal
    previous_sales: Decimal
    previous_orders: int
    previous_fees: Decimal
    # the payouts of the marketplaces whose payouts are read; null when none is
    paid_out: Decimal | None = None
    by_source: list[SourceMoney]
    by_type: list[FeeTypeMoney]
    settlements: list[Settlement]


class OrderFees(BaseModel):
    id: uuid.UUID
    order_label: str
    source: OrderSource
    ordered_at: UtcDateTime
    currency: str
    sales: Decimal
    commission: Decimal
    delivery: Decimal
    other: Decimal
    fees: Decimal


class OrderFeesList(BaseModel):
    items: list[OrderFees]
    total: int


class ProductFees(BaseModel):
    key: str
    name: str
    sku: str | None
    offer_id: str | None
    image_url: str | None
    quantity: int
    orders: int
    sales: Decimal
    fees: Decimal


class ProductFeesList(BaseModel):
    items: list[ProductFees]
