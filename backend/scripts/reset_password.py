#!/usr/bin/env python3
"""Set a new password for an existing Anvero user.

Usage:
    python scripts/reset_password.py EMAIL

Asks for the password twice without echoing it. Never put the password on the
command line: it would land in the shell history and the process list. Like
create_user.py, this only works for someone with access to this machine and
its database.
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import HTTPException
from pydantic import ValidationError

from app.db.session import SessionLocal
from app.repositories.user_repository import UserRepository
from app.schemas.user import MIN_PASSWORD_LENGTH, UserCreate
from app.services.user_service import UserService


def _read_password() -> str:
    if not sys.stdin.isatty():
        # piped input: one line, no confirm. utf-8-sig for the same reason as
        # in create_user.py: Windows PowerShell prefixes piped text with a BOM.
        return sys.stdin.buffer.readline().decode("utf-8-sig").rstrip("\r\n")

    password = getpass.getpass(f"New password (at least {MIN_PASSWORD_LENGTH} characters): ")
    if password != getpass.getpass("Repeat password: "):
        print("Passwords do not match.", file=sys.stderr)
        raise SystemExit(1)
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset an Anvero user's password")
    parser.add_argument("email")
    args = parser.parse_args()

    try:
        data = UserCreate(email=args.email, password=_read_password())
    except ValidationError as exc:
        # field names only: the password must never be echoed back
        fields = sorted({".".join(str(p) for p in err["loc"]) for err in exc.errors()})
        print(f"Invalid {', '.join(fields)}.", file=sys.stderr)
        if "password" in fields:
            print(
                f"The password must be at least {MIN_PASSWORD_LENGTH} characters.",
                file=sys.stderr,
            )
        return 1

    db = SessionLocal()
    try:
        user = UserService(UserRepository(db)).set_password(data.email, data.password)
    except HTTPException as exc:
        print(exc.detail, file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"Password changed for {user.email}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
