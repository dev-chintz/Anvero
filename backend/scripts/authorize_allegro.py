#!/usr/bin/env python3
"""Authorize the Allegro application once and save the refresh token.

Usage:
    python scripts/authorize_allegro.py

Needs ALLEGRO_CLIENT_ID, ALLEGRO_CLIENT_SECRET and ALLEGRO_USER_AGENT in
backend/.env, and
ALLEGRO_AUTH_URL pointing at the environment the application is registered in
(sandbox or production). Prints a link; open it logged in as the seller whose
orders Anvero should import, and confirm. The refresh token is then written to
ALLEGRO_REFRESH_TOKEN in backend/.env rather than printed, so it does not end
up in the terminal's scrollback. See docs/INTEGRATIONS.md.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import set_key

from app.core.config import BACKEND_DIR, settings
from app.integrations.allegro.authorization import (
    AllegroDeviceAuthorizer,
    AuthorizationDenied,
    AuthorizationExpired,
)
from app.integrations.base import IntegrationAuthError, IntegrationError

ENV_FILE = BACKEND_DIR / ".env"


def main(
    authorizer: AllegroDeviceAuthorizer | None = None, env_file: Path = ENV_FILE
) -> int:
    if not (
        settings.allegro_client_id
        and settings.allegro_client_secret
        and settings.allegro_user_agent
    ):
        print(
            "Set ALLEGRO_CLIENT_ID, ALLEGRO_CLIENT_SECRET and ALLEGRO_USER_AGENT in "
            "backend/.env first; see docs/INTEGRATIONS.md.",
            file=sys.stderr,
        )
        return 2
    if not env_file.is_file():
        print(
            f"{env_file} does not exist; run scripts\\bootstrap.ps1 first.",
            file=sys.stderr,
        )
        return 2

    authorizer = authorizer or AllegroDeviceAuthorizer(
        client_id=settings.allegro_client_id,
        client_secret=settings.allegro_client_secret,
        auth_url=settings.allegro_auth_url,
        user_agent=settings.allegro_user_agent,
    )

    print(f"Authorizing against {settings.allegro_auth_url}")
    try:
        authorization = authorizer.start()
        print()
        print("Open this link, logged in as the SELLER account, and confirm:")
        print(f"    {authorization.verification_uri_complete}")
        print(f"The page should show the code {authorization.user_code}.")
        print()
        print(
            f"Waiting for confirmation (up to {authorization.expires_in // 60} minutes, "
            "Ctrl+C to stop)..."
        )
        refresh_token = authorizer.wait_for_refresh_token(authorization)
    except KeyboardInterrupt:
        print("Stopped; nothing was saved.", file=sys.stderr)
        return 130
    except AuthorizationDenied as exc:
        print(f"Not authorized: {exc}", file=sys.stderr)
        return 3
    except AuthorizationExpired as exc:
        print(f"Not authorized: {exc}", file=sys.stderr)
        return 1
    except IntegrationAuthError as exc:
        print(f"Allegro refused the credentials: {exc}", file=sys.stderr)
        return 3
    except IntegrationError as exc:
        print(f"Authorization failed: {exc}", file=sys.stderr)
        return 1

    # the token works once before Allegro rotates it; losing it here would
    # mean authorizing again, so say so plainly if the file cannot be written
    try:
        set_key(env_file, "ALLEGRO_REFRESH_TOKEN", refresh_token, quote_mode="never")
    except OSError as exc:
        print(
            f"Authorized, but {env_file} could not be written ({exc}). "
            "Run the script again once it is writable.",
            file=sys.stderr,
        )
        return 1

    print(f"Authorized. The refresh token is saved to {env_file}.")
    print(
        "Restart the backend so it reads it; the first import replaces any "
        "token chain stored from an earlier authorization."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
