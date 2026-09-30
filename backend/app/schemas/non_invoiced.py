"""What the API says about the non-invoiced sales record (docs/API.md, "Non-invoiced sales record")."""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.non_invoiced import LedgerKind
from app.models.order import OrderSource
from app.schemas.types import UtcDateTime
from app.services.non_invoiced.classifier import Category


class LedgerOverrideRead(BaseModel):
    category: Category
    note: str | None = None
    by: str | None = None
    at: UtcDateTime | None = None


class LedgerRowRead(BaseModel):
    id: uuid.UUID
    kind: LedgerKind
    entry_date: date
    entry_at: UtcDateTime
    source: OrderSource
    order_id: uuid.UUID | None = None
    order_label: str
    order_external_id: str
    corrects_entry_id: uuid.UUID | None = None
    buyer_name: str | None = None
    buyer_address: str | None = None
    amount: Decimal
    currency: str
    # the category it counts in, the classifier's own, and why
    category: Category
    automatic_category: Category
    reason: str
    reason_text: str
    ruleset: str
    override: LedgerOverrideRead | None = None
    locked: bool
    in_report: bool
    # dated in a range already handed over, written after it; carried by this report
    late: bool
    payment_operator: str | None = None
    payout_date: date | None = None


class CategoryTotalRead(BaseModel):
    category: Category
    label: str
    sales: int
    sales_amount: Decimal
    corrections: int
    corrections_amount: Decimal
    total: Decimal


class ChecksRead(BaseModel):
    to_review: int
    needs_register: int
    unmatched_payments: int
    unmatched_amount: Decimal
    untraced_sales: int
    blocking: bool
    warnings: bool


class LimitRead(BaseModel):
    year: int
    total: Decimal
    limit: Decimal
    share: Decimal
    counted_from: date | None = None
    warning: bool
    exceeded: bool


class HandedOverRead(BaseModel):
    id: uuid.UUID
    date_from: date
    date_to: date
    handed_over_at: UtcDateTime
    handed_over_by: str | None = None
    total: Decimal
    currency: str
    row_count: int
    ruleset: str


class NonInvoicedReportRead(BaseModel):
    date_from: date
    date_to: date
    rows: list[LedgerRowRead]
    # the rows the report lists (its export), in its order
    listed: list[uuid.UUID]
    total: Decimal
    currency: str
    totals: list[CategoryTotalRead]
    checks: ChecksRead
    limit: LimitRead
    handed_over: HandedOverRead | None = None
    overlapping: list[HandedOverRead] = Field(default_factory=list)
    # whether the range has ended, and whether nothing stands in the way of handing it over
    # (warnings aside, which the one handing it over acknowledges)
    ended: bool
    can_hand_over: bool


class OverrideIn(BaseModel):
    category: Category
    note: str = Field(min_length=1, max_length=2000)


class HandOverIn(BaseModel):
    date_from: date
    date_to: date
    # the one handing it over has read the warnings (sales needing the register, payments not
    # accounted for) and hands it over all the same
    acknowledged: bool = False


class ExportColumnRead(BaseModel):
    key: str
    label: str
    personal: bool


class ExportColumnList(BaseModel):
    items: list[ExportColumnRead]
    default: list[str]
