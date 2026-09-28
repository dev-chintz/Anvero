#!/usr/bin/env python3
"""Encrypt the integration secrets already stored in the database.

Usage:
    python scripts/encrypt_secrets.py --new-key   # print a new SECRETS_KEY
    python scripts/encrypt_secrets.py             # encrypt what is stored

Setting it up on a machine (docs/GDPR.md, "Secrets"):
1. Run with --new-key and put the printed value in backend/.env as SECRETS_KEY
   (on the NAS, in the backend's environment in the compose file). Every backend
   sharing one database needs the same key. Keep a copy in the password manager:
   without it the secrets cannot be read, and Allegro has to be authorized and
   the secrets entered again.
2. Restart the backend, then run this without arguments.

Running it again changes nothing. Secrets saved after the key is set are
encrypted as they are saved, so this is only for what was stored before.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, text
from sqlalchemy.orm.attributes import flag_modified

from app.core import secrets
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.integration import IntegrationCredential, IntegrationSettings
from app.models.marketplace_write import AppSetting
from app.services.inpost_settings import TOKEN_KEY


def main() -> int:
    parser = argparse.ArgumentParser(description="Encrypt the integration secrets in the database")
    parser.add_argument("--new-key", action="store_true", help="print a new key and change nothing")
    args = parser.parse_args()

    if args.new_key:
        print(secrets.new_key())
        return 0
    if not settings.secrets_key.strip():
        print("SECRETS_KEY is not set; run with --new-key first.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        encrypted = 0
        # the columns decrypt on reading, so what is stored is looked at raw
        for model, key_column in (
            (IntegrationCredential, "refresh_token"),
            (IntegrationSettings, "client_secret"),
        ):
            table = model.__tablename__
            raw = dict(db.execute(text(f"SELECT provider, {key_column} FROM {table}")).all())
            for row in db.scalars(select(model)):
                if raw.get(row.provider) and not secrets.is_encrypted(raw[row.provider]):
                    # written back as it is, which the column encrypts
                    flag_modified(row, key_column)
                    encrypted += 1
                    print(f"{table}.{key_column} ({row.provider})")
        inpost = db.get(AppSetting, TOKEN_KEY)
        if inpost is not None and inpost.value and not secrets.is_encrypted(inpost.value):
            inpost.value = secrets.encrypt(inpost.value)
            encrypted += 1
            print(f"app_settings.{TOKEN_KEY}")
        db.commit()
    finally:
        db.close()

    print(f"{encrypted} secret(s) encrypted." if encrypted else "Nothing left to encrypt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
