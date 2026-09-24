"""After-sales cases: what each asks of the seller and by when, and the sync
that keeps them."""

from datetime import UTC, datetime, timedelta

import pytest

from app.integrations.allegro.after_sales import (
    CLOSED_ISSUE_STATUSES,
    OPEN_ISSUE_STATUSES,
)
from app.models.after_sales import AfterSalesCase, CaseAction, CaseKind
from app.models.order import OrderSource
from app.repositories.after_sales_repository import AfterSalesRepository
from app.schemas.after_sales import SyncedCase
from app.services import after_sales, allegro_sync
from app.services.after_sales import (
    COMMISSION_CLAIM_DAYS,
    RETURN_DECISION_DAYS,
    AfterSalesSyncService,
    classify,
    run_after_sales_sync,
)

# `session` comes from tests/conftest.py

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def _case(kind=CaseKind.RETURN, external_id="X1", status="DELIVERED", opened=None, **fields):
    return SyncedCase(
        kind=kind,
        external_id=external_id,
        status=status,
        opened_at=opened or NOW - timedelta(days=2),
        order_external_id="order-1",
        **fields,
    )


# --- the rules --------------------------------------------------------------


def test_a_return_with_its_goods_back_waits_for_a_decision_within_fourteen_days():
    opened = NOW - timedelta(days=3)

    action, due = classify(_case(status="DELIVERED", opened=opened), NOW)

    assert action is CaseAction.DECIDE
    assert due == opened + timedelta(days=RETURN_DECISION_DAYS)


@pytest.mark.parametrize("status", ["CREATED", "DISPATCHED", "IN_TRANSIT"])
def test_a_return_still_on_its_way_asks_nothing_yet(status):
    assert classify(_case(status=status), NOW) == (CaseAction.NONE, None)


@pytest.mark.parametrize(
    "status",
    ["REJECTED", "FINISHED_APT", "COMMISSION_REFUND_CLAIMED", "COMMISSION_REFUNDED",
     "WAREHOUSE_DELIVERED", "WAREHOUSE_VERIFICATION"],
)
def test_a_return_nobody_has_to_act_on_asks_nothing(status):
    assert classify(_case(status=status), NOW) == (CaseAction.NONE, None)


def test_a_refunded_return_can_have_its_commission_claimed_within_forty_five_days():
    opened = NOW - timedelta(days=10)

    action, due = classify(_case(status="FINISHED", opened=opened), NOW)

    assert action is CaseAction.RECOVER_COMMISSION
    assert due == opened + timedelta(days=COMMISSION_CLAIM_DAYS)


def test_once_the_commission_window_has_closed_there_is_nothing_left_to_do():
    opened = NOW - timedelta(days=COMMISSION_CLAIM_DAYS + 1)

    assert classify(_case(status="FINISHED", opened=opened), NOW) == (CaseAction.NONE, None)


def test_a_submitted_claim_waits_for_a_decision_by_the_deadline_allegro_gives():
    due = NOW + timedelta(days=5)

    action, given = classify(
        _case(CaseKind.CLAIM, status="CLAIM_SUBMITTED", marketplace_due_at=due), NOW
    )

    assert (action, given) == (CaseAction.DECIDE, due)


def test_a_claim_past_its_deadline_still_waits_since_allegro_accepts_it_if_left():
    due = NOW - timedelta(days=1)

    action, given = classify(
        _case(CaseKind.CLAIM, status="CLAIM_SUBMITTED", marketplace_due_at=due), NOW
    )

    assert (action, given) == (CaseAction.DECIDE, due)


@pytest.mark.parametrize("status", ["CLAIM_ACCEPTED", "CLAIM_REJECTED"])
def test_a_decided_claim_asks_nothing(status):
    assert classify(_case(CaseKind.CLAIM, status=status), NOW) == (CaseAction.NONE, None)


@pytest.mark.parametrize("last", ["NEW", "BUYER_REPLIED", "ALLEGRO_ADVISOR_REPLIED", None])
def test_a_dispute_the_seller_did_not_answer_last_waits_for_a_reply(last):
    case = _case(CaseKind.DISPUTE, status="DISPUTE_ONGOING", last_message_status=last)

    assert classify(case, NOW) == (CaseAction.REPLY, None)


def test_a_dispute_the_seller_answered_last_waits_for_the_buyer():
    case = _case(CaseKind.DISPUTE, status="DISPUTE_ONGOING", last_message_status="SELLER_REPLIED")

    assert classify(case, NOW) == (CaseAction.NONE, None)


@pytest.mark.parametrize("status", ["DISPUTE_CLOSED", "DISPUTE_UNRESOLVED"])
def test_a_finished_dispute_asks_nothing(status):
    case = _case(CaseKind.DISPUTE, status=status, last_message_status="BUYER_REPLIED")

    assert classify(case, NOW) == (CaseAction.NONE, None)


# --- the sync ---------------------------------------------------------------


class _FakeAdapter:
    source = OrderSource.ALLEGRO

    def __init__(self, returns=(), open_issues=(), closed_issues=()):
        self.returns = list(returns)
        self.open_issues = list(open_issues)
        self.closed_issues = list(closed_issues)
        self.returns_since = None
        self.closed_since = None

    def fetch_returns(self, since):
        self.returns_since = since
        return self.returns

    def iter_issues(self, statuses, opened_since=None):
        if statuses == OPEN_ISSUE_STATUSES:
            return iter(self.open_issues)
        assert statuses == CLOSED_ISSUE_STATUSES
        self.closed_since = opened_since
        return iter(self.closed_issues)


def _sync(session, adapter, days=90):
    return AfterSalesSyncService(AfterSalesRepository(session), adapter, days).sync(NOW)


def _stored(session, external_id):
    return session.query(AfterSalesCase).filter_by(external_id=external_id).one()


def test_a_sync_stores_each_kind_with_what_it_asks_and_counts_them(session):
    adapter = _FakeAdapter(
        returns=[_case(external_id="R1", status="DELIVERED")],
        open_issues=[
            _case(CaseKind.CLAIM, "C1", "CLAIM_SUBMITTED", marketplace_due_at=NOW + timedelta(days=4)),
            _case(CaseKind.DISPUTE, "D1", "DISPUTE_ONGOING", last_message_status="NEW"),
        ],
        closed_issues=[_case(CaseKind.CLAIM, "C2", "CLAIM_ACCEPTED", is_open=False)],
    )

    result = _sync(session, adapter)

    assert (result.returns, result.claims, result.disputes) == (1, 2, 1)
    assert _stored(session, "R1").action is CaseAction.DECIDE
    assert _stored(session, "C1").due_at is not None
    assert _stored(session, "D1").action is CaseAction.REPLY
    assert _stored(session, "C2").action is CaseAction.NONE


def test_a_second_sync_updates_a_case_and_never_duplicates_it(session):
    _sync(session, _FakeAdapter(returns=[_case(external_id="R1", status="IN_TRANSIT")]))
    assert _stored(session, "R1").action is CaseAction.NONE

    _sync(session, _FakeAdapter(returns=[_case(external_id="R1", status="DELIVERED")]))

    assert session.query(AfterSalesCase).count() == 1
    assert _stored(session, "R1").action is CaseAction.DECIDE


def test_returns_are_read_as_far_back_as_the_period(session):
    adapter = _FakeAdapter()

    _sync(session, adapter, days=30)

    assert adapter.returns_since == NOW - timedelta(days=30)
    assert adapter.closed_since == NOW - timedelta(days=30)


def test_returns_reach_back_to_the_oldest_one_still_open_here(session):
    old = NOW - timedelta(days=120)
    _sync(session, _FakeAdapter(returns=[_case(external_id="R1", status="DELIVERED", opened=old)]))
    adapter = _FakeAdapter()

    _sync(session, adapter, days=30)

    assert adapter.returns_since == old


def test_an_open_claim_allegro_no_longer_lists_as_open_is_closed_here(session):
    _sync(
        session,
        _FakeAdapter(
            open_issues=[
                _case(CaseKind.CLAIM, "C1", "CLAIM_SUBMITTED", marketplace_due_at=NOW),
                _case(CaseKind.DISPUTE, "D1", "DISPUTE_ONGOING", last_message_status="NEW"),
            ]
        ),
    )

    # both left the open list; the claim was decided long ago, so it is not
    # in the closed list either (older than the period), the dispute is
    _sync(
        session,
        _FakeAdapter(closed_issues=[_case(CaseKind.DISPUTE, "D1", "DISPUTE_CLOSED", is_open=False)]),
    )

    claim, dispute = _stored(session, "C1"), _stored(session, "D1")
    assert (claim.is_open, claim.action, claim.due_at) == (False, CaseAction.NONE, None)
    assert (dispute.is_open, dispute.status, dispute.action) == (False, "DISPUTE_CLOSED", CaseAction.NONE)


def test_a_return_is_never_closed_only_because_it_was_not_read_again(session):
    _sync(session, _FakeAdapter(returns=[_case(external_id="R1", status="DELIVERED")]))

    _sync(session, _FakeAdapter())

    stored = _stored(session, "R1")
    assert (stored.is_open, stored.action) == (True, CaseAction.DECIDE)


# --- running it -------------------------------------------------------------


def test_a_second_sync_is_refused_while_one_holds_the_lock(session):
    assert allegro_sync.import_lock.acquire(blocking=False)
    try:
        with pytest.raises(allegro_sync.ImportAlreadyRunning):
            run_after_sales_sync(session)
    finally:
        allegro_sync.import_lock.release()


def test_the_lock_is_released_after_a_sync_that_failed(session, monkeypatch):
    def broken(db):
        raise RuntimeError("boom")

    monkeypatch.setattr(after_sales, "build_after_sales_sync_service", broken)

    with pytest.raises(RuntimeError):
        run_after_sales_sync(session)

    assert allegro_sync.import_lock.acquire(blocking=False)
    allegro_sync.import_lock.release()
