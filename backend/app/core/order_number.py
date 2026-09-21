"""Anvero's own order numbers: how they read, and how a typed one is understood.

The number is a plain integer in the database (`orders.order_number`); the
prefix and the zero padding exist only here, so changing how it reads later
needs no migration.
"""

PREFIX = "AN-"
WIDTH = 6


def format_order_number(number: int) -> str:
    return f"{PREFIX}{number:0{WIDTH}d}"


def parse_order_number(text: str) -> int | None:
    """The number a search term names, or None if it does not name one.

    Accepts what a person would type or copy: `AN-000123`, `an-123`, `000123`
    or `123`. Anything else (an email, a marketplace id with letters) is not
    an order number and is left to the other search fields.
    """
    text = text.strip()
    if text.upper().startswith(PREFIX):
        text = text[len(PREFIX):]
    if not text.isascii() or not text.isdigit():
        return None
    number = int(text)
    # beyond what an integer column holds is no number of ours
    return number if 0 < number <= 2**31 - 1 else None
