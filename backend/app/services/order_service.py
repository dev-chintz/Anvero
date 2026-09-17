import uuid
from datetime import date

from fastapi import HTTPException, status

from app.models.order import Order, OrderSource, OrderStatus, OrderStatusHistory
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

        Raises:
            HTTPException: 409 if this source already has an order with that
                external_id.

        Returns:
            The persisted Order instance, including generated id and
            timestamps.
        """
        if self.repository.get_by_external_id(data.source, data.external_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Order {data.external_id} from {data.source.value} "
                    "already exists"
                ),
            )

        order = Order(
            external_id=data.external_id,
            source=data.source,
            status=data.status,
            customer_email=data.customer_email,
            total_amount=data.total_amount,
            currency=data.currency,
        )
        # only set when given: an explicit None would insert NULL into a
        # required column instead of letting the database default to now
        if data.ordered_at is not None:
            order.ordered_at = data.ordered_at
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

    def update_order_status(
        self,
        order_id: uuid.UUID,
        new_status: OrderStatus,
        changed_by_user_id: int | None = None,
    ) -> Order:
        """Move an order to a new status.

        Any status may be set from any other: operators need to correct
        mistakes, and the valid transitions for this business are not
        settled yet. Add a state machine here once they are.

        Args:
            order_id: The internal primary key of the order.
            new_status: The status to move the order to.
            changed_by_user_id: The user making the change, recorded in the
                status history.

        Raises:
            HTTPException: 404 if no order exists with that id.

        Returns:
            The updated Order, with updated_at refreshed.
        """
        order = self.get_order(order_id)
        return self.repository.update_status(
            order, new_status, changed_by_user_id=changed_by_user_id
        )

    def get_status_history(self, order_id: uuid.UUID) -> list[OrderStatusHistory]:
        """List an order's status transitions, most recent first.

        Args:
            order_id: The internal primary key of the order.

        Raises:
            HTTPException: 404 if no order exists with that id, so an unknown
                id is distinguishable from an order that never moved.

        Returns:
            The recorded transitions; empty if the order is still in the
            status it was created with.
        """
        self.get_order(order_id)
        return self.repository.list_status_history(order_id)

    def list_orders(
        self,
        skip: int = 0,
        limit: int = 100,
        source: OrderSource | None = None,
        status_filter: OrderStatus | None = None,
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        cancellation_warning: bool = False,
    ) -> tuple[list[Order], int]:
        """List orders with optional filtering and pagination.

        All filters combine; the page and the reported total are built from
        the same predicates.

        Args:
            skip: Number of records to skip (offset).
            limit: Maximum number of records to return.
            source: Optional marketplace source to filter by.
            status_filter: Optional order status to filter by.
            search: Optional substring matched against external_id and
                customer_email.
            date_from: Optional inclusive lower bound on the order date, as a
                calendar day in the business timezone.
            date_to: Optional inclusive upper bound on the order date, as a
                calendar day in the business timezone.
            cancellation_warning: When true, only orders cancelled on their
                marketplace whose Anvero status is not yet CANCELLED.

        Returns:
            A tuple of (matching orders for the current page, total count
            of matching orders across all pages).
        """
        filters = {
            "source": source,
            "status": status_filter,
            "search": search,
            "date_from": date_from,
            "date_to": date_to,
            "cancellation_warning": cancellation_warning,
        }
        orders = self.repository.list(skip=skip, limit=limit, **filters)
        total = self.repository.count(**filters)
        return orders, total

    def get_stats(self) -> dict:
        """Aggregate figures for the dashboard, computed across all orders."""
        return self.repository.stats()
