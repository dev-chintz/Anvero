#!/usr/bin/env python3
"""Catch up Allegro orders whose status got stuck behind the marketplace.

Before this fix, an import that saw a fulfillment status move (for example to
`SENT`) could be blocked from applying it by a guard comparing
`orders.status_set_at` against Allegro's own `updatedAt` - a field that does
not reliably move for a fulfillment-only change (`INTEGRATIONS.md`). Once
blocked, `orders.marketplace_status` was still updated to the new value, so
every later import compared the marketplace's status against an
already-caught-up `marketplace_status` and saw no further move: the order
stayed stuck on its old `status` for good. See `DECISIONS.md`.

This is a one-time catch-up for orders already stuck that way. It never
touches an order where `status` is *ahead* of `marketplace_status` (an order
settled to DELIVERED by carrier tracking while Allegro still says SENT is
correct as is, DECISIONS.md 2026-09-26) or a cancellation (handled by the
import's own warning, not silently here).

Usage:
    python scripts/reconcile_stuck_status.py          # dry run, lists what would move
    python scripts/reconcile_stuck_status.py --apply   # applies it
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.models.order import Order, OrderSource, OrderStatus
from app.repositories.order_repository import OrderRepository

# The fulfillment lifecycle's forward order; CANCELLED does not fit on it and
# is left alone here.
_RANK = {
    OrderStatus.NEW: 0,
    OrderStatus.CONFIRMED: 1,
    OrderStatus.READY_FOR_SHIPMENT: 2,
    OrderStatus.SHIPPED: 3,
    OrderStatus.DELIVERED: 4,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="apply the catch-up instead of listing it")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        repository = OrderRepository(db)
        candidates = (
            db.query(Order)
            .filter(
                Order.source == OrderSource.ALLEGRO,
                Order.deleted_at.is_(None),
                Order.status != Order.marketplace_status,
            )
            .all()
        )
        stuck = [
            order
            for order in candidates
            if order.marketplace_status in _RANK
            and order.status in _RANK
            and _RANK[order.status] < _RANK[order.marketplace_status]
        ]

        if not stuck:
            print("No stuck orders found.")
            return 0

        for order in stuck:
            print(
                f"{order.external_id}: {order.status.value} -> {order.marketplace_status.value}"
                f"{' (applying)' if args.apply else ''}"
            )
            if args.apply:
                repository.update_status(order, order.marketplace_status)

        print(f"{len(stuck)} order(s) {'moved' if args.apply else 'would move'}.")
        if not args.apply:
            print("Re-run with --apply to make the change.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
