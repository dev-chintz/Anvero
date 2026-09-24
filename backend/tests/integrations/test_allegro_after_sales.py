"""Allegro's customer returns, disputes and claims: the client's two calls, the
mapping, and the adapter that pages through them.

The payloads follow the examples in Allegro's published OpenAPI specification.
"""

from datetime import UTC, datetime

import httpx2
import pytest

from app.integrations.allegro.after_sales import (
    OPEN_ISSUE_STATUSES,
    AllegroAfterSalesAdapter,
    map_customer_return,
    map_issue,
)
from app.integrations.allegro.client import BETA_ACCEPT_HEADER, AllegroClient
from app.integrations.base import IntegrationAuthError, IntegrationUnavailable
from app.models.after_sales import CaseKind

SINCE = datetime(2026, 6, 1, tzinfo=UTC)


def _return(return_id="R1", status="DELIVERED", created="2026-09-10T09:36:57.00Z", **overrides):
    raw = {
        "id": return_id,
        "createdAt": created,
        "referenceNumber": "1234/Z04A",
        "orderId": "order-1",
        "status": status,
        "buyer": {"email": "user-email@allegro.pl", "login": "User_Login"},
        "items": [
            {
                "offerId": "o1",
                "quantity": 2,
                "name": "Talerz",
                "reason": {"type": "DAMAGED", "userComment": "Pękł w transporcie"},
            },
            {"offerId": "o2", "quantity": 1, "name": "Miska", "reason": {"type": "NONE"}},
        ],
    }
    raw.update(overrides)
    return raw


def _claim(issue_id="C1", status="CLAIM_SUBMITTED", **overrides):
    raw = {
        "id": issue_id,
        "type": "CLAIM",
        "referenceNumber": "1/2025",
        "decisionDueDate": "2026-09-25T12:12:12.019Z",
        "openedDate": "2026-09-10T12:12:12.019Z",
        "subject": None,
        "buyer": {"id": "93975873", "login": "example-user"},
        "checkoutForm": {"id": "order-2", "createdAt": "2026-08-10T15:10:10.019Z"},
        "currentState": {
            "status": status,
            "statusDueDate": "2026-09-24T12:12:12.019Z",
            "returnRequired": True,
            "chatActive": True,
        },
        "chat": {"lastMessage": {"status": "BUYER_REPLIED"}, "messagesCount": 2},
        "expectations": [
            {"name": "PARTIAL_REFUND", "refund": {"amount": "50.00", "currency": "PLN"}}
        ],
        "description": None,
        "reason": {"type": "RECEIVED_ITEMS_NOT_MATCHING_DESCRIPTION", "description": "Free text"},
        "right": "COMPLAINT",
    }
    raw.update(overrides)
    return raw


def _dispute(issue_id="D1", status="DISPUTE_ONGOING", last="BUYER_REPLIED"):
    return {
        "id": issue_id,
        "type": "DISPUTE",
        "referenceNumber": None,
        "decisionDueDate": None,
        "openedDate": "2026-09-10T12:12:12.019Z",
        "subject": "nie otrzymałem towaru po wpłacie",
        "buyer": {"id": "e781964b", "login": "example-user"},
        "checkoutForm": {"id": "order-3"},
        "currentState": {"status": status, "statusDueDate": None, "chatActive": True},
        "chat": {
            "lastMessage": {"status": last},
            "initialMessage": {"text": "hello, where is my parcel"},
        },
        "expectations": [],
    }


# --- the mapping: returns ---------------------------------------------------


def test_a_return_is_read_with_its_goods_reason_and_order():
    case = map_customer_return(_return())

    assert case.kind is CaseKind.RETURN
    assert (case.external_id, case.status, case.is_open) == ("R1", "DELIVERED", True)
    assert case.order_external_id == "order-1"
    assert (case.buyer_login, case.buyer_email) == ("User_Login", "user-email@allegro.pl")
    assert case.summary == "2× Talerz; 1× Miska"
    assert case.reason == "DAMAGED"
    assert case.detail == "Pękł w transporcie"
    assert case.reference_number == "1234/Z04A"


@pytest.mark.parametrize(
    "status, is_open",
    [
        ("CREATED", True),
        ("DISPATCHED", True),
        ("IN_TRANSIT", True),
        ("DELIVERED", True),
        ("COMMISSION_REFUND_CLAIMED", True),
        ("FINISHED", False),
        ("FINISHED_APT", False),
        ("REJECTED", False),
        ("COMMISSION_REFUNDED", False),
    ],
)
def test_a_return_is_over_once_finished_rejected_or_its_commission_refunded(status, is_open):
    assert map_customer_return(_return(status=status)).is_open is is_open


def test_the_no_reason_marker_is_not_a_reason():
    raw = _return(items=[{"name": "Miska", "quantity": 1, "reason": {"type": "NONE"}}])

    assert map_customer_return(raw).reason is None


@pytest.mark.parametrize("field", ["id", "status", "createdAt"])
def test_a_return_without_an_id_a_status_or_a_time_is_skipped(field):
    raw = _return()
    del raw[field]

    assert map_customer_return(raw) is None


def test_a_very_long_goods_list_is_cut_to_what_fits():
    items = [{"name": f"Produkt numer {n} z długą nazwą", "quantity": 1} for n in range(60)]

    case = map_customer_return(_return(items=items))

    assert len(case.summary) <= 500
    assert case.summary.endswith("…")


# --- the mapping: claims and disputes ---------------------------------------


def test_a_claim_carries_its_deadline_reason_and_what_it_asks_for():
    case = map_issue(_claim())

    assert case.kind is CaseKind.CLAIM
    assert (case.external_id, case.status, case.is_open) == ("C1", "CLAIM_SUBMITTED", True)
    assert case.reference_number == "1/2025"
    assert case.order_external_id == "order-2"
    assert case.buyer_login == "example-user"
    assert case.reason == "RECEIVED_ITEMS_NOT_MATCHING_DESCRIPTION"
    assert case.detail == "PARTIAL_REFUND 50.00 PLN"
    # the state's deadline wins over the issue's
    assert case.marketplace_due_at == datetime(2026, 9, 24, 12, 12, 12, 19000, tzinfo=UTC)


def test_a_claims_deadline_falls_back_to_the_issues_decision_date():
    raw = _claim()
    raw["currentState"]["statusDueDate"] = None

    assert map_issue(raw).marketplace_due_at == datetime(2026, 9, 25, 12, 12, 12, 19000, tzinfo=UTC)


def test_a_dispute_has_no_deadline_and_reads_its_opening_message():
    case = map_issue(_dispute())

    assert case.kind is CaseKind.DISPUTE
    assert case.marketplace_due_at is None
    assert case.summary == "hello, where is my parcel"
    assert case.last_message_status == "BUYER_REPLIED"


@pytest.mark.parametrize(
    "status, is_open",
    [
        ("CLAIM_SUBMITTED", True),
        ("DISPUTE_ONGOING", True),
        ("CLAIM_ACCEPTED", False),
        ("CLAIM_REJECTED", False),
        ("DISPUTE_CLOSED", False),
        ("DISPUTE_UNRESOLVED", False),
    ],
)
def test_an_issue_is_open_only_while_ongoing_or_submitted(status, is_open):
    raw = _claim(status=status) if status.startswith("CLAIM") else _dispute(status=status)

    assert map_issue(raw).is_open is is_open


@pytest.mark.parametrize("change", [{"id": None}, {"type": "OTHER"}, {"openedDate": None}])
def test_an_issue_without_an_id_a_known_type_or_a_time_is_skipped(change):
    assert map_issue(_claim(**change)) is None


# --- the client -------------------------------------------------------------


def _client(handler):
    return AllegroClient(
        client_id="id",
        client_secret="secret",
        refresh_token="refresh",
        api_url="https://api.test",
        auth_url="https://auth.test",
        user_agent="anvero-test",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


def _serving(payloads, seen):
    def handler(request):
        if request.url.path == "/token":
            return httpx2.Response(200, json={"access_token": "a", "expires_in": 3600})
        seen.append(request)
        return httpx2.Response(200, json=payloads(request))

    return handler


def test_returns_are_asked_for_with_the_beta_version_and_the_period():
    seen = []
    client = _client(_serving(lambda r: {"count": 1, "customerReturns": [_return()]}, seen))

    returns = client.fetch_customer_returns(SINCE, limit=50, offset=100)

    assert returns == [_return()]
    request = seen[0]
    assert request.url.path == "/order/customer-returns"
    assert request.headers["accept"] == BETA_ACCEPT_HEADER
    assert request.url.params["createdAt.gte"] == "2026-06-01T00:00:00Z"
    assert (request.url.params["limit"], request.url.params["offset"]) == ("50", "100")


def test_issues_are_asked_for_by_status_with_the_beta_version():
    # every /sale/issues resource answers only to the beta header
    # (allegro/allegro-api issue #11711); a public-version request 406s
    seen = []
    client = _client(_serving(lambda r: {"issues": [_claim(), _dispute()]}, seen))

    issues = client.fetch_issues(OPEN_ISSUE_STATUSES, limit=100, offset=0)

    assert len(issues) == 2
    request = seen[0]
    assert request.url.path == "/sale/issues"
    assert request.headers["accept"] == BETA_ACCEPT_HEADER
    assert request.url.params.get_list("status") == OPEN_ISSUE_STATUSES


def test_a_refused_scope_is_an_auth_error_and_a_server_failure_is_unavailable():
    def handler(request):
        if request.url.path == "/token":
            return httpx2.Response(200, json={"access_token": "a", "expires_in": 3600})
        return httpx2.Response(403 if "issues" in request.url.path else 500, json={})

    client = _client(handler)

    with pytest.raises(IntegrationAuthError):
        client.fetch_issues(OPEN_ISSUE_STATUSES)
    with pytest.raises(IntegrationUnavailable):
        client.fetch_customer_returns(SINCE)


def test_a_limit_outside_what_allegro_takes_is_refused_before_asking():
    client = _client(lambda request: httpx2.Response(500))

    with pytest.raises(ValueError):
        client.fetch_issues(OPEN_ISSUE_STATUSES, limit=101)
    with pytest.raises(ValueError):
        client.fetch_customer_returns(SINCE, limit=0)


# --- the adapter ------------------------------------------------------------


class _FakeClient:
    """Serves returns and issues from lists, `limit` at a time."""

    is_configured = True

    def __init__(self, returns=(), issues_by_status=None):
        self.returns = list(returns)
        self.issues_by_status = issues_by_status or {}
        self.issue_calls = []

    def fetch_customer_returns(self, since, limit, offset):
        return self.returns[offset : offset + limit]

    def fetch_issues(self, statuses, limit, offset):
        self.issue_calls.append((tuple(statuses), offset))
        issues = self.issues_by_status[tuple(statuses)]
        return issues[offset : offset + limit]


def test_every_page_of_returns_is_read(monkeypatch):
    import app.integrations.allegro.after_sales as module

    monkeypatch.setattr(module, "MAX_PAGE_SIZE", 2)
    client = _FakeClient(returns=[_return(f"R{n}") for n in range(5)])

    cases = AllegroAfterSalesAdapter(client).fetch_returns(SINCE)

    assert [c.external_id for c in cases] == ["R0", "R1", "R2", "R3", "R4"]


def test_an_unreadable_return_costs_only_itself():
    bad = _return("R2")
    del bad["status"]
    client = _FakeClient(returns=[_return("R1"), bad, _return("R3")])

    cases = AllegroAfterSalesAdapter(client).fetch_returns(SINCE)

    assert [c.external_id for c in cases] == ["R1", "R3"]


def test_open_issues_are_read_to_the_last_page_however_old():
    old = _claim("C-old", openedDate="2020-01-01T00:00:00Z")
    client = _FakeClient(issues_by_status={tuple(OPEN_ISSUE_STATUSES): [_claim("C1"), old]})

    cases = list(AllegroAfterSalesAdapter(client).iter_issues(OPEN_ISSUE_STATUSES))

    assert [c.external_id for c in cases] == ["C1", "C-old"]


def test_closed_issues_stop_at_the_first_one_opened_before_the_period(monkeypatch):
    import app.integrations.allegro.after_sales as module

    monkeypatch.setattr(module, "MAX_PAGE_SIZE", 2)
    statuses = ["CLAIM_ACCEPTED"]
    issues = [
        _claim("C1", status="CLAIM_ACCEPTED", openedDate="2026-09-01T00:00:00Z"),
        _claim("C2", status="CLAIM_ACCEPTED", openedDate="2026-07-01T00:00:00Z"),
        # sorted newest first, so this one and everything after it is too old
        _claim("C3", status="CLAIM_ACCEPTED", openedDate="2026-05-01T00:00:00Z"),
        _claim("C4", status="CLAIM_ACCEPTED", openedDate="2026-04-01T00:00:00Z"),
    ]
    client = _FakeClient(issues_by_status={tuple(statuses): issues})

    cases = list(AllegroAfterSalesAdapter(client).iter_issues(statuses, opened_since=SINCE))

    assert [c.external_id for c in cases] == ["C1", "C2"]
    # the second page was read (C3 sat on it) and no third
    assert client.issue_calls == [(tuple(statuses), 0), (tuple(statuses), 2)]
