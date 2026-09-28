#!/usr/bin/env python3
"""Erase personal data past its retention period, now rather than tonight.

Usage:
    python scripts/apply_retention.py            # show what would be erased
    python scripts/apply_retention.py --apply    # erase it

The backend does this by itself once a day (app/services/retention.py, where
the periods are); this is for seeing what the next run will do, or for a
database no backend is running against. Nothing is deleted: orders keep their
numbers and amounts, and only the fields naming or quoting a person are emptied.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import UTC, datetime

from app.db.session import SessionLocal
from app.services.retention import apply_retention, contact_cutoff, order_cutoff


def main() -> int:
    parser = argparse.ArgumentParser(description="Erase personal data past its retention period")
    parser.add_argument("--apply", action="store_true", help="erase it; without this, only count")
    args = parser.parse_args()

    now = datetime.now(UTC)
    db = SessionLocal()
    try:
        result = apply_retention(db, now, dry_run=not args.apply)
    finally:
        db.close()

    print(f"Orders placed before {order_cutoff(now):%Y-%m-%d %H:%M} UTC: {result.orders}")
    print(f"Message threads quiet since before {contact_cutoff(now):%Y-%m-%d}: {result.threads}")
    print(f"Closed after-sales cases opened before then: {result.cases}")
    print(f"Marketplace writes (old, or of an order above): {result.writes}")
    if args.apply:
        print("Anonymized.")
    elif result.total:
        print("Nothing changed. Run again with --apply to anonymize these.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
