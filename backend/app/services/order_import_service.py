import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from app.integrations.base import MarketplaceAdapter
from app.models.order import Order, OrderStatus
from app.repositories.order_repository import OrderRepository
from app.schemas.order import OrderCreate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImportResult:
    created: int
    updated: int
    # orders newly found cancelled on the marketplace while still active in
    # Anvero: the ones an operator must look at before shipping anything
    cancellation_warnings: int = 0

    @property
    def total(self) -> int:
        return self.created + self.updated


class OrderImportService:
    """Brings marketplace orders into Anvero without losing local decisions."""

    def __init__(self, repository: OrderRepository, adapter: MarketplaceAdapter):
        self.repository = repository
        self.adapter = adapter

    def import_orders(self, limit: int = 100, offset: int = 0) -> ImportResult:
        """Fetch a page of orders and store them.

        Matching is on (source, external_id), so running this twice does not
        duplicate anything.

        An order already present keeps its Anvero status. The status is the
        operator's, set by hand and recorded in the status history; letting a
        sync overwrite it would silently undo their work. The marketplace's
        own status is therefore only used when the order is first seen.

        The one marketplace change that cannot wait for the operator to notice
        is a cancellation, since shipping a cancelled order costs money. It is
        recorded on the order as a warning rather than applied as a status.
        """
        created = 0
        updated = 0
        cancellation_warnings = 0

        for data in self.adapter.fetch_orders(limit=limit, offset=offset):
            cancelled = data.status is OrderStatus.CANCELLED
            existing = self.repository.get_by_external_id(
                data.source, data.external_id
            )
            if existing is None:
                self.repository.create(self._to_order(data))
                created += 1
                continue

            newly_warned = (
                cancelled
                and existing.marketplace_cancelled_at is None
                and existing.status is not OrderStatus.CANCELLED
            )
            self.repository.update_imported_fields(
                existing,
                customer_email=data.customer_email,
                total_amount=data.total_amount,
                currency=data.currency,
                cancelled_on_marketplace=cancelled,
            )
            updated += 1

            if newly_warned:
                cancellation_warnings += 1
                logger.warning(
                    "Order %s was cancelled on %s but is %s in Anvero",
                    data.external_id,
                    data.source.value,
                    existing.status.value,
                )

        logger.info(
            "Imported from %s: %d created, %d updated, %d cancellation warnings",
            self.adapter.source.value,
            created,
            updated,
            cancellation_warnings,
        )
        return ImportResult(
            created=created,
            updated=updated,
            cancellation_warnings=cancellation_warnings,
        )

    @staticmethod
    def _to_order(data: OrderCreate) -> Order:
        cancelled = data.status is OrderStatus.CANCELLED
        return Order(
            external_id=data.external_id,
            source=data.source,
            status=data.status,
            customer_email=data.customer_email,
            total_amount=data.total_amount,
            currency=data.currency,
            # a new order arrives with status CANCELLED already, so no warning
            # shows; the timestamp still records what the marketplace said
            marketplace_cancelled_at=datetime.now(UTC) if cancelled else None,
        )
