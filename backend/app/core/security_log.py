"""The security log: who got in, who was turned away, who changed an account (docs/GDPR.md).

One line to an event, on the logger `security`: `event key=value ...`. An account is named by
its number, never by its e-mail. What is typed at the login form for an account that does not
exist is whatever a stranger types, or a password typed into the e-mail field by mistake, and an
e-mail copied into a log is one more place the application keeps a person's address. The number
says which account; the list of accounts says who.
"""

import logging

logger = logging.getLogger("security")

LOGIN_SUCCEEDED = "login_succeeded"
LOGIN_FAILED = "login_failed"
RATE_LIMITED = "rate_limited"
ACCOUNT_CREATED = "account_created"
ACCOUNT_CHANGED = "account_changed"

# who made a change that did not come through the API: a script run on the server
CONSOLE = "console"

_MAX_VALUE = 64


def _clean(value: object) -> str:
    """One word: nothing a value holds can end the line or start another.

    A client address comes from a header and a path from the request, so neither is trusted to be
    free of line breaks. Control characters are dropped and every run of white space (a line break
    included) becomes one underscore.
    """
    printable = "".join(ch for ch in str(value) if ch.isprintable() or ch.isspace())
    return "_".join(printable.split())[:_MAX_VALUE] or "-"


def actor(user_id: int | None) -> int | str:
    """Who made a change: an administrator by number, or the console when no account did."""
    return CONSOLE if user_id is None else user_id


def record(event: str, level: int = logging.INFO, **fields: object) -> None:
    """Write one event. A field that is None is left out."""
    parts = [event, *(f"{key}={_clean(value)}" for key, value in fields.items() if value is not None)]
    logger.log(level, " ".join(parts))
