"""The non-invoiced sales report: an order classified for accounting, and the summary of a period.

Ported from a standalone tool (`docs/PROJECT_STATUS.md`, "temp"): only its two APPROVED business
decisions are implemented (a complete company invoice excludes; a cancelled or suspended order
that was never paid in full excludes as out of scope). Everything else is `MANUAL_REVIEW`, exactly
as the ported tool leaves it, rather than guessing an unapproved rule — see `docs/DECISIONS.md`.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel

from app.models.order import OrderSource


class SalesReportCategory(str, Enum):
    RETAIL = "RETAIL"
    COMPANY = "COMPANY"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class SalesReportRow(BaseModel):
    # Anvero's own id, when the row comes from an imported order; null for a row read only from
    # an uploaded CSV, once that path exists
    order_id: uuid.UUID | None = None
    order_label: str | None = None
    source: OrderSource
    order_external_id: str
    ordered_at: datetime
    # the buyer's login only, never their name, address or phone: enough for accounting to trace
    # the order back on the marketplace, without the report carrying more personal data than it
    # needs (`ROADMAP.md`, "GDPR (RODO): to do", point 4)
    buyer_login: str | None = None
    amount: Decimal
    currency: str

    category: SalesReportCategory
    included: bool
    reason: str
    # the rule that decided it, e.g. "INV-001"; null while nothing has, which cannot happen once
    # ManualReviewRule's fallback always runs, kept anyway for a row a future source might skip it
    rule_id: str | None = None

    # set once an operator has overridden the automatic decision
    overridden: bool = False
    override_note: str | None = None


class SalesReportSummary(BaseModel):
    total: int
    retail: int
    company: int
    out_of_scope: int
    manual_review: int


class SalesReportList(BaseModel):
    date_from: date
    date_to: date
    summary: SalesReportSummary
    items: list[SalesReportRow]


class SalesReportOverrideIn(BaseModel):
    included: bool
    note: str | None = None
