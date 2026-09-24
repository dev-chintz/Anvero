"""Returns, claims and disputes: what each asks of the seller, and by when.

Allegro gives a claim its deadline; it gives a return none, so the deadlines of
a return come from the rules below, and are only as right as they are. They are
deliberately the early end of what the law allows, so a warning comes too soon
and not too late. Runs under the same lock as an order import
(app.services.allegro_sync.import_lock), like the message sync: the same
rotating token is refreshed.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.allegro.after_sales import (
    CLOSED_ISSUE_STATUSES,
    OPEN_ISSUE_STATUSES,
    AllegroAfterSalesAdapter,
)
from app.models.after_sales import CaseAction, CaseKind
from app.repositories.after_sales_repository import AfterSalesRepository
from app.schemas.after_sales import AfterSalesSyncResult, SyncedCase
from app.services.allegro_import import build_allegro_client
from app.services.allegro_sync import ImportAlreadyRunning, import_lock

logger = logging.getLogger(__name__)

# The seller refunds a return within 14 days. The law counts them from the
# buyer's declaration (the goods may be held back until they arrive), and the
# declaration is what `createdAt` is, so this is the outer limit, not a guess
# about when the goods came back.
RETURN_DECISION_DAYS = 14
# How long the sales commission of a refunded return can be claimed back. The
# owner's figure, from AlleIntegrator's rules; Allegro's API does not give it,
# and it is counted from the declaration for the same early-end reason.
COMMISSION_CLAIM_DAYS = 45

# dispute messages after which the buyer is waiting for the seller
_SELLER_HAS_REPLIED = "SELLER_REPLIED"


def classify(case: SyncedCase, now: datetime) -> tuple[CaseAction, datetime | None]:
    """What the case asks of the seller, and the moment it is due by.

    A return waits for a decision once its goods are back (`DELIVERED`); after
    the refund (`FINISHED`) the commission can be claimed until its window
    closes, after which there is nothing left to do. A claim waits for the
    seller's decision until it is decided, by the deadline Allegro gives it;
    one left undecided is accepted by Allegro, which is why a late one still
    counts as waiting. A dispute waits for a reply whenever the seller did not
    write last; one with no last-message status counts as waiting, so a field
    Allegro stops filling in raises alarms and does not hide them.
    """
    if case.kind is CaseKind.RETURN:
        if case.status == "DELIVERED":
            return CaseAction.DECIDE, case.opened_at + timedelta(days=RETURN_DECISION_DAYS)
        if case.status == "FINISHED":
            due = case.opened_at + timedelta(days=COMMISSION_CLAIM_DAYS)
            if due > now:
                return CaseAction.RECOVER_COMMISSION, due
        return CaseAction.NONE, None
    if case.kind is CaseKind.CLAIM:
        if case.status == "CLAIM_SUBMITTED":
            return CaseAction.DECIDE, case.marketplace_due_at
        return CaseAction.NONE, None
    if case.status == "DISPUTE_ONGOING" and case.last_message_status != _SELLER_HAS_REPLIED:
        return CaseAction.REPLY, None
    return CaseAction.NONE, None


class AfterSalesSyncService:
    def __init__(
        self,
        repository: AfterSalesRepository,
        adapter: AllegroAfterSalesAdapter,
        days: int | None = None,
    ):
        self.repository = repository
        self.adapter = adapter
        self.days = days if days is not None else settings.allegro_after_sales_days

    def sync(self, now: datetime | None = None) -> AfterSalesSyncResult:
        now = now or datetime.now(UTC)
        source = self.adapter.source
        window = now - timedelta(days=self.days)

        # returns: back as far as the window, or as far as the oldest one
        # still open here, whichever is older, so how it ended is seen
        oldest_open = self.repository.oldest_open_return(source)
        returns = self.adapter.fetch_returns(min(window, oldest_open) if oldest_open else window)

        # disputes and claims: every open one however old, and the closed ones
        # of the window; a claim reopened counts from when it was reopened
        open_issues = list(self.adapter.iter_issues(OPEN_ISSUE_STATUSES))
        closed_issues = list(self.adapter.iter_issues(CLOSED_ISSUE_STATUSES, opened_since=window))

        counts = {CaseKind.RETURN: 0, CaseKind.CLAIM: 0, CaseKind.DISPUTE: 0}
        for case in [*returns, *open_issues, *closed_issues]:
            action, due_at = classify(case, now)
            self.repository.upsert(source, case, action, due_at)
            counts[case.kind] += 1
        # an open dispute or claim that Allegro no longer lists as open is closed
        closed = self.repository.close_issues_not_in(source, {c.external_id for c in open_issues})
        self.repository.commit()

        logger.info(
            "Allegro after-sales synced: %d returns, %d claims, %d disputes, %d closed since",
            counts[CaseKind.RETURN],
            counts[CaseKind.CLAIM],
            counts[CaseKind.DISPUTE],
            closed,
        )
        return AfterSalesSyncResult(
            returns=counts[CaseKind.RETURN],
            claims=counts[CaseKind.CLAIM],
            disputes=counts[CaseKind.DISPUTE],
        )


def build_after_sales_sync_service(db: Session) -> AfterSalesSyncService:
    return AfterSalesSyncService(
        AfterSalesRepository(db), AllegroAfterSalesAdapter(build_allegro_client(db))
    )


def run_after_sales_sync(db: Session) -> AfterSalesSyncResult:
    """Run one sync, sharing the import lock so it never races a token refresh.

    Raises ImportAlreadyRunning without waiting if an order import, a message
    sync or another one of these is under way.
    """
    if not import_lock.acquire(blocking=False):
        raise ImportAlreadyRunning
    try:
        return build_after_sales_sync_service(db).sync()
    finally:
        import_lock.release()
