import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.order import OrderSource, OrderStatus
from app.repositories.order_repository import OrderRepository
from app.schemas.order import (
    OrderCreate,
    OrderListResponse,
    OrderRead,
    OrderStats,
    OrderStatusHistoryRead,
    OrderUpdate,
)
from app.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get("", response_model=OrderListResponse)
def list_orders(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    source: OrderSource | None = Query(default=None),
    status: OrderStatus | None = Query(default=None),
    search: str | None = Query(default=None, max_length=255),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    cancellation_warning: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    service = OrderService(OrderRepository(db))
    orders, total = service.list_orders(
        skip=skip,
        limit=limit,
        source=source,
        status_filter=status,
        search=search,
        date_from=date_from,
        date_to=date_to,
        cancellation_warning=cancellation_warning,
    )
    return OrderListResponse(items=orders, total=total, skip=skip, limit=limit)


# must stay above /{order_id} or "stats" is parsed as a UUID path param
@router.get("/stats", response_model=OrderStats)
def get_order_stats(db: Session = Depends(get_db)):
    service = OrderService(OrderRepository(db))
    return service.get_stats()


@router.get("/{order_id}", response_model=OrderRead)
def get_order(order_id: uuid.UUID, db: Session = Depends(get_db)):
    service = OrderService(OrderRepository(db))
    return service.get_order(order_id)


@router.get("/{order_id}/history", response_model=list[OrderStatusHistoryRead])
def get_order_status_history(order_id: uuid.UUID, db: Session = Depends(get_db)):
    service = OrderService(OrderRepository(db))
    return service.get_status_history(order_id)


# path follows the contract in docs/API.md: status is its own sub-resource
# because a change here is meant to record an entry in the status history
@router.patch("/{order_id}/status", response_model=OrderRead)
def update_order_status(
    order_id: uuid.UUID, payload: OrderUpdate, db: Session = Depends(get_db)
):
    service = OrderService(OrderRepository(db))
    return service.update_order_status(order_id, payload.status)


@router.post("", response_model=OrderRead)
def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    # intended for local/manual testing until marketplace ingestion exists
    service = OrderService(OrderRepository(db))
    return service.create_order(order)
