"""Allegro's customer returns, claims and disputes, read for the after-sales queue.

Kept apart from adapter.py for the same reason messaging is: these are
resources of their own, read on their own, not part of an order import. Built
from Allegro's published OpenAPI specification (customer returns under
`/order/customer-returns`, still beta; disputes and claims under `/sale/issues`);
see INTEGRATIONS.md, "Returns and claims".
"""

import logging
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from app.integrations.allegro.client import MAX_PAGE_SIZE, AllegroClient
from app.integrations.base import IntegrationUnavailable
from app.integrations.mapping import build as _build
from app.integrations.mapping import obj as _obj
from app.integrations.mapping import text as _text
from app.models.after_sales import CaseKind
from app.models.order import OrderSource
from app.schemas.after_sales import SyncedCase

logger = logging.getLogger(__name__)

# a safety stop, not a limit anyone should meet in one sync
MAX_PAGES = 200

# statuses of a return that need nothing more from anyone
_RETURN_CLOSED = {"FINISHED", "FINISHED_APT", "REJECTED", "COMMISSION_REFUNDED"}

OPEN_ISSUE_STATUSES = ["CLAIM_SUBMITTED", "DISPUTE_ONGOING"]
CLOSED_ISSUE_STATUSES = ["CLAIM_ACCEPTED", "CLAIM_REJECTED", "DISPUTE_CLOSED", "DISPUTE_UNRESOLVED"]

_MAX_TEXT = 500


def _shorten(value: str | None) -> str | None:
    if value is None or len(value) <= _MAX_TEXT:
        return value
    return value[: _MAX_TEXT - 1].rstrip() + "…"


def map_customer_return(raw: dict[str, Any]) -> SyncedCase | None:
    """One entry of GET /order/customer-returns, or None without an id, a
    status or a creation time (a case that cannot be placed in time cannot be
    given a deadline)."""
    return_id = _text(raw.get("id"))
    if return_id is None:
        return None
    status = _text(raw.get("status"))
    raw_items = raw.get("items")
    items = [i for i in raw_items if isinstance(i, dict)] if isinstance(raw_items, list) else []

    parts = []
    for item in items:
        name = _text(item.get("name"))
        if name:
            quantity = item.get("quantity")
            parts.append(f"{quantity}× {name}" if isinstance(quantity, int) else name)
    reasons = [_obj(item.get("reason")) for item in items]
    reason = next((_text(r.get("type")) for r in reasons if _text(r.get("type"))), None)
    comment = next((_text(r.get("userComment")) for r in reasons if _text(r.get("userComment"))), None)
    buyer = _obj(raw.get("buyer"))

    return _build(
        SyncedCase,
        return_id,
        "customer return",
        {
            "kind": CaseKind.RETURN,
            "external_id": return_id,
            "status": status,
            "is_open": status not in _RETURN_CLOSED,
            "opened_at": _text(raw.get("createdAt")),
            "reference_number": _text(raw.get("referenceNumber")),
            "order_external_id": _text(raw.get("orderId")),
            "buyer_login": _text(buyer.get("login")),
            "buyer_email": _text(buyer.get("email")),
            # NONE is Allegro's "no reason given", not a reason
            "reason": None if reason == "NONE" else reason,
            "summary": _shorten("; ".join(parts) or None),
            "detail": _shorten(comment),
        },
        label="Return",
    )


def _expectation_text(expectations: Any) -> str | None:
    """What a claim asks for, like `REFUND 50.00 PLN` or `REPAIR`."""
    if not isinstance(expectations, list):
        return None
    texts = []
    for expectation in expectations:
        item = _obj(expectation)
        name = _text(item.get("name"))
        if name is None:
            continue
        refund = _obj(item.get("refund"))
        amount, currency = _text(refund.get("amount")), _text(refund.get("currency"))
        texts.append(f"{name} {amount} {currency}" if amount and currency else name)
    return ", ".join(texts) or None


def map_issue(raw: dict[str, Any]) -> SyncedCase | None:
    """One entry of GET /sale/issues (a dispute or a claim), or None without an
    id, a type, a status or an opening time."""
    issue_id = _text(raw.get("id"))
    kind = _text(raw.get("type"))
    if issue_id is None or kind not in ("DISPUTE", "CLAIM"):
        return None
    state = _obj(raw.get("currentState"))
    status = _text(state.get("status"))
    chat = _obj(raw.get("chat"))
    initial = _text(_obj(chat.get("initialMessage")).get("text"))
    # a claim's deadline is on the state; the issue also carries the date the
    # decision is due, which is the fallback
    due = _text(state.get("statusDueDate")) or _text(raw.get("decisionDueDate"))

    return _build(
        SyncedCase,
        issue_id,
        "issue",
        {
            "kind": CaseKind(kind),
            "external_id": issue_id,
            "status": status,
            "is_open": status in OPEN_ISSUE_STATUSES,
            "opened_at": _text(raw.get("openedDate")),
            "reference_number": _text(raw.get("referenceNumber")),
            "order_external_id": _text(_obj(raw.get("checkoutForm")).get("id")),
            "buyer_login": _text(_obj(raw.get("buyer")).get("login")),
            "reason": _text(_obj(raw.get("reason")).get("type")),
            "summary": _shorten(_text(raw.get("description")) or initial or _text(raw.get("subject"))),
            "detail": _shorten(_expectation_text(raw.get("expectations"))),
            "marketplace_due_at": due if kind == "CLAIM" else None,
            "last_message_status": _text(_obj(chat.get("lastMessage")).get("status")),
        },
        label="Issue",
    )


class AllegroAfterSalesAdapter:
    source = OrderSource.ALLEGRO

    def __init__(self, client: AllegroClient | None = None):
        self._client = client or AllegroClient()

    @property
    def is_configured(self) -> bool:
        return self._client.is_configured

    def fetch_returns(self, since: datetime) -> list[SyncedCase]:
        """Every return created since `since`, all pages of them."""
        cases: list[SyncedCase] = []
        for page in range(MAX_PAGES):
            raw = self._client.fetch_customer_returns(since, MAX_PAGE_SIZE, page * MAX_PAGE_SIZE)
            for item in raw:
                case = map_customer_return(item)
                if case is None:
                    logger.warning("Skipping an Allegro customer return that could not be mapped")
                else:
                    cases.append(case)
            if len(raw) < MAX_PAGE_SIZE:
                return cases
        raise IntegrationUnavailable(
            f"Allegro returned more than {MAX_PAGES * MAX_PAGE_SIZE} customer returns; "
            "narrow the period and try again"
        )

    def iter_issues(
        self, statuses: list[str], opened_since: datetime | None = None
    ) -> Iterator[SyncedCase]:
        """Disputes and claims in `statuses`, newest opened first.

        With `opened_since` reading stops at the first one opened earlier:
        Allegro lists them by descending opening date, so nothing later can be
        newer. Without it every page is read, which is what open cases need
        however old they are.
        """
        for page in range(MAX_PAGES):
            raw = self._client.fetch_issues(statuses, MAX_PAGE_SIZE, page * MAX_PAGE_SIZE)
            for item in raw:
                case = map_issue(item)
                if case is None:
                    logger.warning("Skipping an Allegro dispute or claim that could not be mapped")
                    continue
                if opened_since is not None and case.opened_at < opened_since:
                    return
                yield case
            if len(raw) < MAX_PAGE_SIZE:
                return
        raise IntegrationUnavailable(
            f"Allegro returned more than {MAX_PAGES * MAX_PAGE_SIZE} disputes and claims; "
            "narrow the period and try again"
        )
