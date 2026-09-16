import uuid

from fastapi import HTTPException, status

from app.models.order import Order, OrderSource, OrderStatus
from app.repositories.order_repository import OrderRepository
from app.schemas.order import OrderCreate


class OrderService:
    """Business logic for marketplace orders.

    Wraps the OrderRepository to enforce validation and error handling
    that shouldn't leak into the API layer or the persistence layer.
    """

    def __init__(self, repository: OrderRepository):
        self.repository = repository

    def create_order(self, data: OrderCreate) -> Order:
        """Create a new order from validated input data.

        Args:
            data: Validated order payload (see OrderCreate schema).

        Returns:
            The persisted Order instance, including generated id and
            timestamps.
        """
        order = Order(
            external_id=data.external_id,
            source=data.source,
            status=data.status,
            customer_email=data.customer_email,
            total_amount=data.total_amount,
            currency=data.currency,
        )
        return self.repository.create(order)

    def get_order(self, order_id: uuid.UUID) -> Order:
        """Fetch a single order by its internal UUID.

        Args:
            order_id: The internal primary key of the order.

        Raises:
            HTTPException: 404 if no order exists with that id.

        Returns:
            The matching Order instance.
        """
        order = self.repository.get(order_id)
        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )
        return order

    def list_orders(
        self,
        skip: int = 0,
        limit: int = 100,
        source: OrderSource | None = None,
        status_filter: OrderStatus | None = None,
    ) -> tuple[list[Order], int]:
        """List orders with optional filtering and pagination.

        Filtering by source and status is mutually applicable (both can be
        set at once, though the current API only allows one at a time).

        Args:
            skip: Number of records to skip (offset).
            limit: Maximum number of records to return.
            source: Optional marketplace source to filter by.
            status_filter: Optional order status to filter by.

        Returns:
            A tuple of (matching orders for the current page, total count
            of matching orders across all pages).
        """
        if source is not None:
            orders = self.repository.list_by_source(source, skip=skip, limit=limit)
        elif status_filter is not None:
            orders = self.repository.list_by_status(
                status_filter, skip=skip, limit=limit
            )
        else:
            orders = self.repository.list_all(skip=skip, limit=limit)

        total = self.repository.count(source=source, status=status_filter)
        return orders, total
