"""Erli's payments and payouts as payment operations, for the non-invoiced sales record
(docs/NON_INVOICED_SALES.md, stage 7).

Built from Erli's published API description (erli.pl/svc/shop-api/doc, read 2026-10-01), not yet
run against the real service. Erli collects the buyer's money itself, through PayU, and pays it out
to the seller's bank account:

- `POST /payments/operations/_search` with `type` `payment` lists the buyers' payments: `id`,
  `orderIds` (the orders it paid for), `amount` in **złoty** (unlike the rest of Erli's money, in
  grosze), `status` (`COMPLETED` once paid), `completedAt`, `operator` (`PAYU`). A completed one
  becomes a `CONTRIBUTION`, named by its id; the order names the same id in `payment.id`.
- `POST /payments/payouts/_search` lists the payouts to the bank (amount in grosze), already stored
  as payouts (app/integrations/erli/billing.py); each also becomes a `PAYOUT` operation of the same
  wallet operator, so that a payment is tied to the payout that took it to the bank the same way
  as Allegro's (`link_payout`, FIRST_AFTER).

Refunds are not read yet: Erli lists them as return operations whose shape its description leaves
open.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

from app.integrations.erli.mapper import _grosze, _moment
from app.integrations.mapping import build, text
from app.models.order import OrderSource
from app.schemas.order import PaymentOperationCreate

COMPLETED = "COMPLETED"


def _zloty(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def map_payment(raw: dict[str, Any]) -> PaymentOperationCreate | None:
    """A buyer's completed payment as a CONTRIBUTION, or None if it is not completed or cannot be
    read."""
    payment_id = text(raw.get("id"))
    occurred_at = _moment(raw.get("completedAt"))
    amount = _zloty(raw.get("amount"))
    if text(raw.get("status")) != COMPLETED or payment_id is None or occurred_at is None or amount is None:
        return None
    return build(
        PaymentOperationCreate,
        payment_id,
        "payment",
        {
            "source": OrderSource.ERLI,
            "fingerprint": f"ERLI-PAYMENT-{payment_id}",
            "type": "CONTRIBUTION",
            "group": "INCOME",
            "occurred_at": occurred_at,
            "amount": amount,
            "currency": "PLN",
            "wallet_operator": text(raw.get("operator")),
            "payment_id": payment_id,
        },
        label="Erli",
    )


def map_payout_operation(raw: dict[str, Any]) -> PaymentOperationCreate | None:
    """A payout to the bank as a PAYOUT operation (money out of the wallet, so negative), or None
    if it cannot be read."""
    payout_id = text(raw.get("id"))
    occurred_at = _moment(raw.get("createdAt"))
    amount = _grosze(raw.get("amount"))
    if payout_id is None or occurred_at is None or amount is None:
        return None
    return build(
        PaymentOperationCreate,
        payout_id,
        "payout operation",
        {
            "source": OrderSource.ERLI,
            "fingerprint": f"ERLI-PAYOUT-{payout_id}",
            "type": "PAYOUT",
            "group": "OUTCOME",
            "occurred_at": occurred_at,
            "amount": -amount,
            "currency": text(raw.get("currency")) or "PLN",
            "wallet_operator": text(raw.get("operator")),
            "payout_id": payout_id,
        },
        label="Erli",
    )
