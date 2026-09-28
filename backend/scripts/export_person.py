#!/usr/bin/env python3
"""Export everything Anvero holds about one buyer, for a GDPR access or
portability request (docs/GDPR.md).

Usage:
    python scripts/export_person.py --login LOGIN [--email EMAIL] [--out FILE]

The buyer is found by marketplace login, e-mail, or both (ignoring case). The
result is JSON: their orders with addresses, items, shipments and labels, what
was sent to a marketplace about those orders, their message threads and their
after-sales cases. Without --out it goes to the screen.

The file holds the buyer's personal data: hand it to them, then delete it.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.services.personal_data import export_person, find_person


def main() -> int:
    parser = argparse.ArgumentParser(description="Export what Anvero holds about one buyer")
    parser.add_argument("--login", help="the buyer's marketplace login")
    parser.add_argument("--email", help="the buyer's e-mail")
    parser.add_argument("--out", type=Path, help="the JSON file to write; the screen if left out")
    args = parser.parse_args()
    if not args.login and not args.email:
        parser.error("give --login, --email or both")

    db = SessionLocal()
    try:
        person = find_person(db, login=args.login, email=args.email)
        data = export_person(db, person)
    finally:
        db.close()

    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(
            f"{len(data['orders'])} orders, {len(data['message_threads'])} message threads, "
            f"{len(data['after_sales_cases'])} after-sales cases written to {args.out}.",
            file=sys.stderr,
        )
        print("The file holds personal data: delete it once handed over.", file=sys.stderr)
    else:
        print(text)
    if person.empty:
        print("Nothing is held under that login or e-mail.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
