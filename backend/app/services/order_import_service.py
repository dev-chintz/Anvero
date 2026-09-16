import logging
from dataclasses import dataclass

from app.integrations.base import MarketplaceAdapter
from app.models.order import Order
from app.repositories.order_repository import OrderRepository
from app.schemas.order import OrderCreate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImportResult:
    created: int
    updated: int

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
        """
        created = 0
        updated = 0

        for data in self.adapter.fetch_orders(limit=limit, offset=offset):
            existing = self.repository.get_by_external_id(
                data.source, data.external_id
            )
            if existing is None:
                self.repository.create(self._to_order(data))
                created += 1
            else:
                self.repository.update_imported_fields(
                    existing,
                    customer_email=data.customer_email,
                    total_amount=data.total_amount,
                    currency=data.currency,
                )
                updated += 1

        logger.info(
            "Imported from %s: %d created, %d updated",
            self.adapter.source.value,
            created,
            updated,
        )
        return ImportResult(created=created, updated=updated)

    @staticmethod
    def _to_order(data: OrderCreate) -> Order:
        return Order(
            external_id=data.external_id,
            source=data.source,
            status=data.status,
            customer_email=data.customer_email,
            total_amount=data.total_amount,
            currency=data.currency,
        )
