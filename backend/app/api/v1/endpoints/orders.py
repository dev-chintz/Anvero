import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.order import OrderSource, OrderStatus
from app.repositories.order_repository import OrderRepository
from app.schemas.order import OrderCreate, OrderListResponse, OrderRead
from app.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get("", response_model=OrderListResponse)
def list_orders(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    source: OrderSource | None = Query(default=None),
    status: OrderStatus | None = Query(default=None),
    db: Session = Depends(get_db),
):
    service = OrderService(OrderRepository(db))
    orders, total = service.list_orders(
        skip=skip,
        limit=limit,
        source=source,
        status_filter=status,
    )
    return OrderListResponse(items=orders, total=total, skip=skip, limit=limit)


@router.get("/{order_id}", response_model=OrderRead)
def get_order(order_id: uuid.UUID, db: Session = Depends(get_db)):
    service = OrderService(OrderRepository(db))
    return service.get_order(order_id)


@router.post("", response_model=OrderRead)
def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    # intended for local/manual testing until marketplace ingestion exists
    service = OrderService(OrderRepository(db))
    return service.create_order(order)
