#!/usr/bin/env python3
"""Create a user who can log in to Anvero.

Usage:
    python scripts/create_user.py EMAIL

Asks for the password twice without echoing it. There is no registration
endpoint: accounts exist only because someone with access to this machine ran
this script.
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
        # piped input, e.g. from a provisioning script: one line, no confirm.
        # Read as bytes and decode with utf-8-sig: Windows PowerShell prefixes
        # piped text with a byte-order mark, which would otherwise become an
        # invisible first character of the stored password, so that typing
        # the same password at the login form could never match it.
        return sys.stdin.buffer.readline().decode("utf-8-sig").rstrip("\r\n")

    password = getpass.getpass(f"Password (at least {MIN_PASSWORD_LENGTH} characters): ")
    if password != getpass.getpass("Repeat password: "):
        print("Passwords do not match.", file=sys.stderr)
        raise SystemExit(1)
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an Anvero user")
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
        user = UserService(UserRepository(db)).create_user(data)
    except HTTPException as exc:
        print(exc.detail, file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"Created user {user.email}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
