import logging

from app.integrations.allegro.client import AllegroClient
from app.integrations.allegro.mapper import OrderMappingError, map_checkout_form
from app.models.order import OrderSource
from app.schemas.order import OrderCreate

logger = logging.getLogger(__name__)


class AllegroAdapter:
    """Allegro's side of the MarketplaceAdapter protocol."""

    source = OrderSource.ALLEGRO

    def __init__(self, client: AllegroClient | None = None):
        self._client = client or AllegroClient()

    @property
    def is_configured(self) -> bool:
        return self._client.is_configured

    def fetch_orders(self, limit: int = 100, offset: int = 0) -> list[OrderCreate]:
        checkout_forms = self._client.fetch_checkout_forms(limit=limit, offset=offset)

        orders: list[OrderCreate] = []
        for checkout_form in checkout_forms:
            try:
                orders.append(map_checkout_form(checkout_form))
            except OrderMappingError as exc:
                # one unusable order must not cost us the rest of the page;
                # it is logged so the gap is visible rather than silent
                logger.warning("Skipping Allegro order that could not be mapped: %s", exc)

        return orders
