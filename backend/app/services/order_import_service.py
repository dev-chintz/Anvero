import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.integrations.base import MarketplaceAdapter
from app.models.order import Order, OrderStatus
from app.repositories.integration_credential_repository import (
    IntegrationCredentialRepository,
)
from app.repositories.order_repository import OrderRepository
from app.schemas.order import OrderCreate
from app.services.order_details import apply_details

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

    def __add__(self, other: "ImportResult") -> "ImportResult":
        return ImportResult(
            created=self.created + other.created,
            updated=self.updated + other.updated,
            cancellation_warnings=self.cancellation_warnings + other.cancellation_warnings,
        )


# Allegro stamps an order's change time itself, and a moment lost between its
# clock and ours must not leave an order out of two consecutive runs
SYNC_OVERLAP = timedelta(minutes=5)


class OrderImportService:
    """Brings marketplace orders into Anvero without losing local decisions."""

    def __init__(
        self,
        repository: OrderRepository,
        adapter: MarketplaceAdapter,
        credentials: IntegrationCredentialRepository | None = None,
        initial_days: int = 7,
    ):
        self.repository = repository
        self.adapter = adapter
        # where the point the last sync reached is kept; only sync_orders
        # needs it
        self.credentials = credentials
        self.initial_days = initial_days

    def sync_orders(self, days: int | None = None) -> ImportResult:
        """Fetch what is new or changed since the last successful sync.

        The first time - nothing recorded yet - it reaches back `initial_days`
        by purchase date; `days` forces that window again regardless of what
        is recorded, for a backfill. Every later run asks only for orders
        changed since the recorded point, which covers new orders and updates
        to old ones alike, and pages through all of them.

        The point moves forward only when every page was fetched and stored,
        and it moves to when this run *started*, less SYNC_OVERLAP, so an
        order changed while the run was in progress is caught by the next.
        A run that fails part way leaves it where it was: the pages already
        stored stay stored, and the next run repeats them harmlessly, since
        matching is by (source, external_id).
        """
        if self.credentials is None:
            raise RuntimeError("sync_orders needs the credential repository")

        provider = self.adapter.source.value
        started_at = datetime.now(UTC)
        recorded = self.credentials.last_synced_at(provider)

        if days is not None or recorded is None:
            window = days if days is not None else self.initial_days
            filters = {"bought_since": started_at - timedelta(days=window)}
            logger.info("Importing %s orders bought in the last %d days", provider, window)
        else:
            filters = {"updated_since": recorded}
            logger.info("Importing %s orders changed since %s", provider, recorded)

        result = ImportResult(created=0, updated=0)
        for orders in self.adapter.iter_order_pages(**filters):
            result += self._store(orders)

        if not self.credentials.set_last_synced_at(provider, started_at - SYNC_OVERLAP):
            logger.warning(
                "No stored credentials for %s, so the sync point was not recorded; "
                "the next import starts from the beginning again",
                provider,
            )
        return result

    def import_orders(self, limit: int = 100, offset: int = 0) -> ImportResult:
        """Fetch one page of orders and store them, whatever their age.

        Does not read or move the sync point; `sync_orders` is what the
        interface uses.
        """
        return self._store(self.adapter.fetch_orders(limit=limit, offset=offset))

    def _store(self, orders: list[OrderCreate]) -> ImportResult:
        """Store orders that have already been fetched.

        Matching is on (source, external_id), so running this twice does not
        duplicate anything.

        An order already present follows the marketplace: when the status the
        marketplace reports has moved since the last import, the Anvero status
        moves to it and the change is recorded in the status history (with no
        author, since no one made it). Only a *move* is applied - the status
        the marketplace reported last time is kept in `marketplace_status` for
        exactly that comparison - so a status the operator set by hand stands
        until the marketplace itself changes its mind, instead of being
        reverted by every import that happens to see the order again.

        A cancellation is applied like any other move, and is also counted in
        `cancellation_warnings` when it takes an active order to CANCELLED, so
        the operator hears about it: shipping a cancelled order costs money.
        """
        created = 0
        updated = 0
        cancellation_warnings = 0

        for data in orders:
            cancelled = data.status is OrderStatus.CANCELLED
            existing = self.repository.get_by_external_id(
                data.source, data.external_id
            )
            if existing is None:
                self.repository.create(self._to_order(data))
                created += 1
                continue

            # compared before the import overwrites what it is compared with
            status_moved = data.status != existing.marketplace_status
            # the marketplace owns the details as well; staged here and
            # committed together with the fields below
            apply_details(existing, data)
            self.repository.update_imported_fields(
                existing,
                customer_email=data.customer_email,
                total_amount=data.total_amount,
                currency=data.currency,
                cancelled_on_marketplace=cancelled,
                ordered_at=data.ordered_at,
                marketplace_status=data.status,
                marketplace_status_label=data.marketplace_status_label,
            )
            updated += 1

            if not status_moved or data.status == existing.status:
                continue

            previous = existing.status
            self.repository.update_status(existing, data.status)
            logger.info(
                "Order %s moved from %s to %s to follow %s",
                data.external_id,
                previous.value,
                data.status.value,
                data.source.value,
            )
            if cancelled:
                cancellation_warnings += 1
                logger.warning(
                    "Order %s was cancelled on %s and was %s in Anvero",
                    data.external_id,
                    data.source.value,
                    previous.value,
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
        order = Order(
            external_id=data.external_id,
            source=data.source,
            status=data.status,
            # the same value to begin with; they part company when the
            # operator moves one or the marketplace the other
            marketplace_status=data.status,
            marketplace_status_label=data.marketplace_status_label,
            customer_email=data.customer_email,
            total_amount=data.total_amount,
            currency=data.currency,
            # a new order arrives with status CANCELLED already, so no warning
            # shows; the timestamp still records what the marketplace said
            marketplace_cancelled_at=datetime.now(UTC) if cancelled else None,
        )
        # without a purchase time from the marketplace the database default
        # (now) applies; an explicit None would insert NULL instead
        if data.ordered_at is not None:
            order.ordered_at = data.ordered_at
        apply_details(order, data)
        return order
