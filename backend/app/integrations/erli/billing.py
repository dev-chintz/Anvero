"""Erli's billing account: its fees, its taking them out of the proceeds, and its payouts.

Checked against the real service on 2026-09-27. `POST /billing/company/entries`
lists every movement on the seller's account with Erli, in grosze, newest id
first. Most of them are fees, but not all: the account also records rebates set
aside, amounts blocked, money added for campaigns. Erli's own dictionary
(`GET /dictionaries/billingEntryTypes`) says what each kind is by its
`fiscalFunction`:

- `plusCharges`: a fee (commission, payment handling, delivery, subscription,
  promotion), negative;
- `minusCharges`: a fee given back (a rebate used on the commission), positive;
- `plusPayments`: Erli taking the fees out of the proceeds, or a transfer to pay
  them; a settlement, not a fee.

Only those three are kept; the rest move money between Erli's own sub-accounts
and would count twice. The dictionary is read on every import, so a kind Erli
adds later is sorted by what Erli says it is.
"""

import logging
from typing import Any

from app.integrations.erli.mapper import _grosze, _moment
from app.integrations.mapping import build, text
from app.models.order import OrderSource
from app.schemas.order import BillingEntryCreate, PayoutCreate

logger = logging.getLogger(__name__)

FEES = frozenset({"plusCharges", "minusCharges"})
SETTLEMENTS = frozenset({"plusPayments"})


class BillingType:
    def __init__(self, label: str | None, fiscal_function: str | None):
        self.label = label
        self.fiscal_function = fiscal_function


def map_billing_types(raw: list[Any]) -> dict[str, BillingType]:
    """Erli's dictionary of billing entry types, by type."""
    types: dict[str, BillingType] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        code = text(item.get("type"))
        if code:
            types[code] = BillingType(
                text(item.get("displayLabel")) or text(item.get("description")),
                text(item.get("fiscalFunction")),
            )
    return types


def map_billing_entry(raw: dict[str, Any], types: dict[str, BillingType]) -> BillingEntryCreate | None:
    """One entry of Erli's billing account, or None when it is not a fee or a settlement.

    `productId` is Erli's id of the item, which Anvero keeps as the item's
    `external_id`; it is stored as the entry's offer so the fee can be put on
    the product it is for.
    """
    code = text(raw.get("type"))
    kind = types.get(code) if code else None
    if kind is None or kind.fiscal_function not in FEES | SETTLEMENTS:
        return None
    entry_id = text(raw.get("id"))
    occurred_at = _moment(raw.get("occurredAt"))
    amount = _grosze(raw.get("amount"))
    if entry_id is None or occurred_at is None or amount is None:
        return None
    return build(
        BillingEntryCreate,
        entry_id,
        "billing entry",
        {
            "source": OrderSource.ERLI,
            "external_id": entry_id,
            "occurred_at": occurred_at,
            "type_id": code,
            "type_name": kind.label or text(raw.get("description")),
            "amount": amount,
            "currency": text(raw.get("currency")) or "PLN",
            "order_external_id": text(raw.get("orderId")),
            "offer_id": text(raw.get("productId")),
            "is_settlement": kind.fiscal_function in SETTLEMENTS,
        },
        label="Erli",
    )


def is_known_other(raw: dict[str, Any], types: dict[str, BillingType]) -> bool:
    """An entry of a kind Erli names but that is neither a fee nor a settlement."""
    code = text(raw.get("type"))
    return bool(code) and code in types and types[code].fiscal_function not in FEES | SETTLEMENTS


def map_payout(raw: dict[str, Any]) -> PayoutCreate | None:
    """One payout to the seller's bank account, or None if it cannot be read."""
    payout_id = text(raw.get("id"))
    paid_at = _moment(raw.get("createdAt"))
    amount = _grosze(raw.get("amount"))
    if payout_id is None or paid_at is None or amount is None:
        return None
    return build(
        PayoutCreate,
        payout_id,
        "payout",
        {
            "source": OrderSource.ERLI,
            "external_id": payout_id,
            "paid_at": paid_at,
            "amount": amount,
            "currency": text(raw.get("currency")) or "PLN",
            "operator": text(raw.get("operator")),
        },
        label="Erli",
    )
