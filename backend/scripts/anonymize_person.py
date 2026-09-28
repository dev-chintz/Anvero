#!/usr/bin/env python3
"""Erase one buyer's personal data, for a GDPR erasure request (docs/GDPR.md).

Usage:
    python scripts/anonymize_person.py --login LOGIN [--email EMAIL]           # show what
    python scripts/anonymize_person.py --login LOGIN [--email EMAIL] --apply   # erase it

The buyer is found as scripts/export_person.py finds them; run that first if
they also asked for a copy. Orders keep their numbers, amounts and items. An
order still inside its tax period keeps a company invoice's name, tax id and
address, which the law requires kept; the daily retention run erases those
once the period is over. Nothing here can be undone.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.services.personal_data import anonymize_person, find_person


def main() -> int:
    parser = argparse.ArgumentParser(description="Erase one buyer's personal data")
    parser.add_argument("--login", help="the buyer's marketplace login")
    parser.add_argument("--email", help="the buyer's e-mail")
    parser.add_argument("--apply", action="store_true", help="erase it; without this, only show")
    args = parser.parse_args()
    if not args.login and not args.email:
        parser.error("give --login, --email or both")

    db = SessionLocal()
    try:
        person = find_person(db, login=args.login, email=args.email)
        if person.empty:
            print("Nothing is held under that login or e-mail.")
            return 0
        print(f"Orders: {len(person.orders)}")
        for order in person.orders:
            print(f"  {order.source.value} {order.external_id}, {order.ordered_at:%Y-%m-%d}")
        print(f"Message threads: {len(person.threads)}")
        print(f"After-sales cases: {len(person.cases)}")
        if not args.apply:
            print("Nothing changed. Run again with --apply to erase this; it cannot be undone.")
            return 0
        result = anonymize_person(db, person)
    finally:
        db.close()

    print(
        f"Erased: {result.orders} orders, {result.threads} message threads, "
        f"{result.cases} after-sales cases."
    )
    if result.invoices_kept:
        print(
            f"{result.invoices_kept} company invoice(s) kept for the tax period; "
            "the daily retention run erases them after it."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
