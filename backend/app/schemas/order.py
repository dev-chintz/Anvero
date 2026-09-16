import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.order import OrderSource, OrderStatus


class OrderBase(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    source: OrderSource
    customer_email: EmailStr
    total_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="PLN", min_length=3, max_length=3)


class OrderCreate(OrderBase):
    status: OrderStatus = OrderStatus.NEW


class OrderUpdate(BaseModel):
    status: OrderStatus


class OrderRead(OrderBase):
    id: uuid.UUID
    status: OrderStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# kept as an alias to match the requested naming in the task spec
OrderResponse = OrderRead


class OrderListResponse(BaseModel):
    items: list[OrderRead]
    total: int
    skip: int
    limit: int


class OrderStats(BaseModel):
    total_orders: int
    total_revenue: Decimal
    this_week: int
    pending: int
    by_status: dict[str, int]
    by_source: dict[str, int]
