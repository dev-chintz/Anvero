import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.order import OrderSource, OrderStatus
from app.models.user import User
from app.repositories.order_repository import OrderQueue, OrderRepository, OrderSort
from app.schemas.order import (
    OrderBillingRead,
    OrderCreate,
    OrderDetailRead,
    OrderListResponse,
    OrderStats,
    OrderStatusHistoryRead,
    OrderUpdate,
)
from app.services.order_service import OrderService

# Every order endpoint requires a logged-in user. Set on the router rather
# than per endpoint, so an endpoint added later cannot be left open by
# forgetting a parameter.
router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
    dependencies=[Depends(get_current_user)],
)


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
    queue: OrderQueue | None = Query(default=None),
    sort: OrderSort = Query(default=OrderSort.NEWEST),
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
        queue=queue,
        sort=sort,
    )
    return OrderListResponse(items=orders, total=total, skip=skip, limit=limit)


# must stay above /{order_id} or "stats" is parsed as a UUID path param
@router.get("/stats", response_model=OrderStats)
def get_order_stats(db: Session = Depends(get_db)):
    service = OrderService(OrderRepository(db))
    return service.get_stats()


@router.get("/{order_id}", response_model=OrderDetailRead)
def get_order(order_id: uuid.UUID, db: Session = Depends(get_db)):
    service = OrderService(OrderRepository(db))
    return OrderDetailRead.from_order(service.get_order(order_id))


@router.get("/{order_id}/history", response_model=list[OrderStatusHistoryRead])
def get_order_status_history(order_id: uuid.UUID, db: Session = Depends(get_db)):
    service = OrderService(OrderRepository(db))
    return service.get_status_history(order_id)


@router.get("/{order_id}/billing", response_model=OrderBillingRead)
def get_order_billing(order_id: uuid.UUID, db: Session = Depends(get_db)):
    repository = OrderRepository(db)
    order = OrderService(repository).get_order(order_id)
    entries = repository.list_billing_entries(order)
    return OrderBillingRead(
        entries=entries,
        # an entry in another currency cannot be added to the order's
        total=sum((e.amount for e in entries if e.currency == order.currency), Decimal("0.00")),
        currency=order.currency,
    )


# path follows the contract in docs/API.md: status is its own sub-resource
# because a change here is meant to record an entry in the status history
# returns the details too: the order page replaces its copy of the order with
# this response, and would otherwise lose them
@router.patch("/{order_id}/status", response_model=OrderDetailRead)
def update_order_status(
    order_id: uuid.UUID,
    payload: OrderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrderService(OrderRepository(db))
    order = service.update_order_status(
        order_id, payload.status, changed_by_user_id=current_user.id
    )
    return OrderDetailRead.from_order(order)


@router.post("", response_model=OrderDetailRead)
def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    # intended for local/manual testing until marketplace ingestion exists
    service = OrderService(OrderRepository(db))
    return OrderDetailRead.from_order(service.create_order(order))
