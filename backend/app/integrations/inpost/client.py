"""HTTP client for InPost's ShipX API: parcel lockers, made and printed from Anvero.

Built from InPost's published documentation and the open clients that follow it,
not yet run against the real service (docs/INTEGRATIONS.md, "InPost"). InPost
authenticates with a token made in the Manager Paczek (My account > API), sent
as a bearer token, for one organization; the sandbox is a separate service with
its own tokens, where nothing is sent or billed.

Buying a shipment is asynchronous on InPost's side: creating one answers at once
with what was accepted, and the status and the tracking number follow after a
moment, so `get_shipment` is what tells whether it has one yet. Only shipments
made through this API can be read through it; those made in the Manager Paczek are
not available (InPost's documentation says so), which is why Anvero cannot print
what was made there.
"""

import logging
from typing import Any

import httpx2

from app.integrations.base import (
    IntegrationAuthError,
    IntegrationNotConfigured,
    IntegrationUnavailable,
)

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 30.0

PRODUCTION_URL = "https://api-shipx-pl.easypack24.net"
SANDBOX_URL = "https://sandbox-api-shipx-pl.easypack24.net"

ENVIRONMENTS = {"production": PRODUCTION_URL, "sandbox": SANDBOX_URL}

# a locker takes three sizes (A, B and C at the locker itself)
TEMPLATES = ("small", "medium", "large")

# InPost's own words for a parcel that will not travel: nothing more to do with it
FINAL_STATUSES = frozenset({"cancelled", "delivered", "returned_to_sender", "canceled"})


def _explain(response: httpx2.Response) -> str:
    """What InPost said was wrong, in its own words: a message and the fields it names."""
    try:
        body = response.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    parts: list[str] = []
    message = body.get("message") or body.get("error")
    if isinstance(message, str) and message:
        parts.append(message)
    details = body.get("details")
    if isinstance(details, dict):
        for field, problem in details.items():
            parts.append(f"{field}: {problem}")
    elif isinstance(details, str) and details:
        parts.append(details)
    return "; ".join(parts)[:500]


class InpostClient:
    def __init__(
        self,
        token: str = "",
        organization_id: str = "",
        environment: str = "sandbox",
        http_client: httpx2.Client | None = None,
    ):
        if environment not in ENVIRONMENTS:
            raise ValueError(f"environment must be one of {', '.join(ENVIRONMENTS)}")
        self._token = token
        self._organization_id = organization_id
        self._url = ENVIRONMENTS[environment]
        self._http = http_client or httpx2.Client(timeout=REQUEST_TIMEOUT_SECONDS)

    @property
    def is_configured(self) -> bool:
        return bool(self._token and self._organization_id)

    # ---- what is asked ------------------------------------------------------------

    def get_organization(self) -> dict[str, Any]:
        """The organization the token belongs to: a read, to learn that the token and
        the organization's id go together."""
        return self._json("GET", f"/v1/organizations/{self._organization_id}", what="the organization")

    def create_shipment(self, payload: dict[str, Any]) -> dict[str, Any]:
        """`POST /v1/organizations/{id}/shipments`: what InPost accepted.

        Its status is not the final one and it carries no tracking number yet.
        """
        return self._json(
            "POST",
            f"/v1/organizations/{self._organization_id}/shipments",
            body=payload,
            what="the shipment",
        )

    def get_shipment(self, shipment_id: str) -> dict[str, Any]:
        """`GET /v1/shipments/{id}`: its status now, and its tracking number once it has one."""
        return self._json("GET", f"/v1/shipments/{shipment_id}", what="the shipment")

    def cancel_shipment(self, shipment_id: str) -> None:
        """`DELETE /v1/shipments/{id}`: allowed until InPost has taken the parcel."""
        self._request("DELETE", f"/v1/shipments/{shipment_id}", what="the cancellation")

    def fetch_labels(self, shipment_ids: list[str], label_type: str = "A6") -> bytes:
        """The labels as one PDF, in the order given.

        `A6` is 105 x 148 mm, for a label printer; `normal` is a whole A4 page. One
        shipment is asked for by its own address, several together through the
        organization's batch address; for the batch InPost returns one file when
        they are the same service.
        """
        if not shipment_ids:
            raise ValueError("at least one shipment is needed")
        if len(shipment_ids) == 1:
            response = self._request(
                "GET",
                f"/v1/shipments/{shipment_ids[0]}/label",
                params={"format": "pdf", "type": label_type},
                what="the label",
                accept="application/pdf",
            )
        else:
            response = self._request(
                "POST",
                f"/v1/organizations/{self._organization_id}/shipments/labels",
                body={"shipment_ids": [int(i) if i.isdigit() else i for i in shipment_ids], "format": "pdf", "type": label_type},
                what="the labels",
                accept="application/pdf",
            )
        if not response.content.startswith(b"%PDF"):
            raise IntegrationUnavailable("InPost did not return a PDF for the labels")
        return response.content

    # ---- how it is asked -----------------------------------------------------------

    def _json(self, method: str, path: str, what: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._request(method, path, what=what, body=body)
        try:
            payload = response.json()
        except ValueError as exc:
            raise IntegrationUnavailable(f"InPost did not return JSON for {what}") from exc
        if not isinstance(payload, dict):
            raise IntegrationUnavailable(f"InPost returned something unexpected for {what}")
        return payload

    def _request(
        self,
        method: str,
        path: str,
        what: str,
        body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        accept: str = "application/json",
    ) -> httpx2.Response:
        if not self.is_configured:
            raise IntegrationNotConfigured("InPost is not configured: enter the token and organization in Settings")
        try:
            response = self._http.request(
                method,
                f"{self._url}{path}",
                json=body,
                params=params,
                headers={"Authorization": f"Bearer {self._token}", "Accept": accept},
            )
        except httpx2.HTTPError as exc:
            raise IntegrationUnavailable(f"InPost is unreachable for {what}: {exc}") from exc

        if response.status_code in (401, 403):
            raise IntegrationAuthError(f"InPost refused the token for {what} ({response.status_code})")
        if response.status_code == 429:
            raise IntegrationUnavailable(f"InPost asked to slow down for {what} (429)")
        if response.status_code >= 400:
            explanation = _explain(response)
            raise IntegrationUnavailable(
                f"InPost returned {response.status_code} for {what}" + (f": {explanation}" if explanation else "")
            )
        return response
