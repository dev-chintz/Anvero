import re
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.order import OrderSource, OrderStatus
from app.models.user import User
from app.repositories.order_repository import OrderQueue, OrderRepository, OrderSort
from app.schemas.marketplace_write import MarketplaceWriteRead
from app.schemas.order import (
    OrderBillingRead,
    OrderChangeResult,
    OrderCreate,
    OrderDetailRead,
    OrderListResponse,
    OrderMarksUpdate,
    OrderRead,
    OrderStats,
    OrderStatusHistoryRead,
    OrderUpdate,
    ProductionList,
    ShipmentAdd,
)
from app.services.order_service import OrderService
from app.services.order_writes import ALLEGRO_CARRIERS, OrderWrites
from app.services.production import build_production_list
from app.services.shipping_labels import ShippingLabels

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
    deleted: bool = Query(default=False),
    starred: bool = Query(default=False),
    flagged: bool = Query(default=False),
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
        deleted=deleted,
        starred=starred,
        flagged=flagged,
    )
    return OrderListResponse(items=orders, total=total, skip=skip, limit=limit)


# must stay above /{order_id} or "stats" is parsed as a UUID path param
@router.get("/stats", response_model=OrderStats)
def get_order_stats(db: Session = Depends(get_db)):
    service = OrderService(OrderRepository(db))
    return service.get_stats()


# like /stats, must stay above /{order_id}
@router.get("/production", response_model=ProductionList)
def get_production_list(
    status: OrderStatus | None = Query(default=None),
    search: str | None = Query(default=None, max_length=500),
    db: Session = Depends(get_db),
):
    """What to make, by product, for the orders still to be made.

    `status` narrows it to the orders in one Anvero status; `search` to the orders
    a search finds, where several can be given separated by commas or semicolons
    (`AN-000041, AN-000043`) and an order matching any of them counts.
    """
    terms = re.split(r"[;,\n]", search) if search else []
    return build_production_list(
        OrderRepository(db).list_in_queue_with_items(
            OrderQueue.TO_MAKE, status=status, search_terms=terms
        )
    )


@router.get("/{order_id}", response_model=OrderDetailRead)
def get_order(order_id: uuid.UUID, db: Session = Depends(get_db)):
    service = OrderService(OrderRepository(db))
    return OrderDetailRead.from_order(service.get_order(order_id))


@router.get("/{order_id}/history", response_model=list[OrderStatusHistoryRead])
def get_order_status_history(order_id: uuid.UUID, db: Session = Depends(get_db)):
    service = OrderService(OrderRepository(db))
    return service.get_status_history(order_id)


@router.get("/{order_id}/buyer-orders", response_model=list[OrderRead])
def get_buyer_orders(order_id: uuid.UUID, db: Session = Depends(get_db)):
    repository = OrderRepository(db)
    order = OrderService(repository).get_order(order_id)
    return repository.list_buyer_orders(order)


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
@router.patch("/{order_id}/status", response_model=OrderChangeResult)
def update_order_status(
    order_id: uuid.UUID,
    payload: OrderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrderService(OrderRepository(db))
    previous = service.get_order(order_id).status
    order = service.update_order_status(
        order_id, payload.status, changed_by_user_id=current_user.id
    )
    # the marketplace hears of it too (or, in safe mode, the log does)
    write = None
    if order.status != previous:
        write = OrderWrites(db).push_status(order, current_user.id)
    return _change_result(order, write)


@router.patch("/{order_id}/marks", response_model=OrderDetailRead)
def update_order_marks(order_id: uuid.UUID, payload: OrderMarksUpdate, db: Session = Depends(get_db)):
    """Star or flag an order. The marks are the operator's own: nothing is sent to a
    marketplace, and an order that is deleted can still be marked."""
    service = OrderService(OrderRepository(db))
    return OrderDetailRead.from_order(
        service.set_marks(order_id, payload.starred, payload.flagged)
    )


@router.delete("/{order_id}", response_model=OrderDetailRead)
def delete_order(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Take the order out of every list. The row is kept, so it can be restored
    and an import does not bring it back; a bought label stops it."""
    service = OrderService(OrderRepository(db))
    order = service.get_order(order_id)
    if order.deleted_at is None and ShippingLabels(db).has_active(order):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The order has a shipping label: cancel the label first",
        )
    return OrderDetailRead.from_order(service.delete_order(order_id, current_user.id))


@router.post("/{order_id}/restore", response_model=OrderDetailRead)
def restore_order(order_id: uuid.UUID, db: Session = Depends(get_db)):
    return OrderDetailRead.from_order(OrderService(OrderRepository(db)).restore_order(order_id))


@router.post("/{order_id}/shipments", response_model=OrderChangeResult)
def add_order_shipment(
    order_id: uuid.UUID,
    payload: ShipmentAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.carrier_id not in ALLEGRO_CARRIERS:
        raise HTTPException(
            status_code=422,
            detail=f"carrier_id must be one of {', '.join(ALLEGRO_CARRIERS)}",
        )
    service = OrderService(OrderRepository(db))
    order = service.get_order(order_id)
    service.ensure_not_deleted(order)
    _, write = OrderWrites(db).add_shipment(
        order, payload.carrier_id, payload.carrier_name, payload.waybill, current_user.id
    )
    return _change_result(order, write)


def _change_result(order, write) -> OrderChangeResult:
    return OrderChangeResult(
        **OrderDetailRead.from_order(order).model_dump(),
        marketplace_write=MarketplaceWriteRead.model_validate(write.record) if write else None,
    )


@router.post("", response_model=OrderDetailRead)
def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    # intended for local/manual testing until marketplace ingestion exists
    service = OrderService(OrderRepository(db))
    return OrderDetailRead.from_order(service.create_order(order))
