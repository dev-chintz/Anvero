"""HTTP client for Erli's Shop API.

Built from Erli's published OpenAPI description (erli.pl/svc/shop-api/doc),
not yet run against the real service. Erli authenticates a shop with one API
key from the seller panel, sent as a bearer token; unlike Allegro's token it
does not rotate, so there is nothing to store between runs.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx2

from app.core.config import settings
from app.integrations.base import (
    IntegrationAuthError,
    IntegrationError,
    IntegrationNotConfigured,
    IntegrationUnavailable,
)

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 30.0

# Erli's maximum for one page of orders
MAX_PAGE_SIZE = 200
# and for one page of its billing account, and of payouts
BILLING_PAGE_SIZE = 500
PAYOUT_PAGE_SIZE = 200


def erli_timestamp(value: datetime) -> str:
    """ISO 8601 in UTC with milliseconds, as Erli's own examples write it."""
    utc = value.astimezone(UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


class ErliClient:
    def __init__(
        self,
        api_key: str | None = None,
        api_url: str | None = None,
        http_client: httpx2.Client | None = None,
    ):
        self._api_key = api_key if api_key is not None else settings.erli_api_key
        self._api_url = (api_url if api_url is not None else settings.erli_api_url).rstrip("/")
        self._http = http_client or httpx2.Client(timeout=REQUEST_TIMEOUT_SECONDS)

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    @property
    def api_key(self) -> str:
        return self._api_key

    def search_orders(
        self,
        after: str | None = None,
        limit: int = MAX_PAGE_SIZE,
        created_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """One page of orders by update time, oldest change first.

        `after` is where the page starts: an ISO timestamp for the first page,
        then the `cursor` of the last order of the previous page, which Erli
        makes unique so orders changed at the same moment are not skipped.
        `created_since` narrows the search to orders placed since then.
        """
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
        pagination: dict[str, Any] = {"sortField": "updated", "order": "ASC", "limit": limit}
        if after is not None:
            pagination["after"] = after
        body: dict[str, Any] = {"pagination": pagination}
        if created_since is not None:
            body["filter"] = {
                "field": "created",
                "operator": ">=",
                "value": erli_timestamp(created_since),
            }

        payload = self._post("/orders/_search", body, "Erli order search")
        if not isinstance(payload, list):
            raise IntegrationUnavailable("Erli order search did not return a list")
        return [order for order in payload if isinstance(order, dict)]

    def fetch_product_image(self, external_id: str) -> str | None:
        """Return the product's first picture, or None if it cannot be read.

        Failure never raises: a picture is not needed for an order to be valid,
        so a deleted product, a refused request or a network error costs the
        item its thumbnail, not the import. GET /products/{externalId} returns
        the product with `images`, a list of `{"url": ...}`; `externalId` is
        the seller's own product id, which the order's item carries.
        """
        try:
            payload = self._request("GET", f"/products/{quote(external_id, safe='')}", None, "Erli product")
        except IntegrationError as exc:
            logger.warning("Erli product %s: image unavailable: %s", external_id, exc)
            return None
        images = payload.get("images") if isinstance(payload, dict) else None
        if isinstance(images, list) and images and isinstance(images[0], dict):
            url = images[0].get("url")
            if isinstance(url, str) and url:
                return url
        return None

    def fetch_billing_types(self) -> list[dict[str, Any]]:
        """Erli's dictionary of billing entry types (GET /dictionaries/billingEntryTypes)."""
        payload = self._request("GET", "/dictionaries/billingEntryTypes", None, "Erli billing types")
        if not isinstance(payload, list):
            raise IntegrationUnavailable("Erli billing types did not return a list")
        return [item for item in payload if isinstance(item, dict)]

    def fetch_billing_entries(
        self, since: datetime, before_id: int | None = None, limit: int = BILLING_PAGE_SIZE
    ) -> list[dict[str, Any]]:
        """One page of the billing account since `since`, newest id first.

        Erli sorts this list only by id, descending; `before_id` continues
        below the last id of the previous page.
        """
        pagination: dict[str, Any] = {"sortField": "id", "order": "DESC", "limit": limit}
        if before_id is not None:
            pagination["after"] = before_id
        payload = self._post(
            "/billing/company/entries",
            {"pagination": pagination, "simpleFilter": {"fromOccurredAt": erli_timestamp(since)}},
            "Erli billing entries",
        )
        if not isinstance(payload, list):
            raise IntegrationUnavailable("Erli billing entries did not return a list")
        return [item for item in payload if isinstance(item, dict)]

    def search_payouts(
        self, since: datetime, after_id: int | None = None, limit: int = PAYOUT_PAGE_SIZE
    ) -> list[dict[str, Any]]:
        """One page of payouts made since `since`, by id ascending."""
        pagination: dict[str, Any] = {"sortField": "id", "order": "ASC", "limit": limit}
        if after_id is not None:
            pagination["after"] = after_id
        payload = self._post(
            "/payments/payouts/_search",
            {
                "pagination": pagination,
                "filter": {"field": "createdAt", "operator": ">=", "value": erli_timestamp(since)},
            },
            "Erli payouts",
        )
        if not isinstance(payload, list):
            raise IntegrationUnavailable("Erli payouts did not return a list")
        return [item for item in payload if isinstance(item, dict)]

    def _post(self, path: str, body: dict[str, Any], what: str) -> Any:
        return self._request("POST", path, body, what)

    def _request(self, method: str, path: str, body: dict[str, Any] | None, what: str) -> Any:
        if not self.is_configured:
            raise IntegrationNotConfigured("ERLI_API_KEY is not set")
        try:
            response = self._http.request(
                method,
                f"{self._api_url}{path}",
                json=body,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Accept": "application/json",
                },
            )
        except httpx2.HTTPError as exc:
            raise IntegrationUnavailable(f"{what}: Erli unreachable: {exc}") from exc

        if response.status_code in (401, 403):
            raise IntegrationAuthError(
                f"{what}: Erli refused the API key ({response.status_code})"
            )
        if response.status_code == 429:
            # Erli's limit moves with its load; the next run tries again
            raise IntegrationUnavailable(f"{what}: Erli asked to slow down (429)")
        if response.status_code >= 400:
            raise IntegrationUnavailable(f"{what}: Erli returned {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise IntegrationUnavailable(f"{what}: Erli did not return JSON") from exc
