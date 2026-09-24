"""Cleaning text that comes from a marketplace."""

import html
import re

# characters that take no room on the page: zero-width space, non-joiner and
# joiner, word joiner and the byte-order mark. Allegro's message editor puts a
# non-joiner (`&zwnj;`) into a message, which is unwanted in a search or a snippet.
_INVISIBLE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")


def clean_marketplace_text(text: str) -> str:
    """The text as a person would read it.

    Allegro's Message Center hands messages over as HTML text: `zam&oacute;wienie`,
    `&quot;`, `&amp;`, `&nbsp;`, a `&zwnj;` between paragraphs. They are decoded here
    (once: a `&amp;lt;` is a literal `&lt;` typed by someone), the invisible
    characters dropped, a no-break space made an ordinary one and the ends trimmed.
    Line breaks are kept.
    """
    decoded = html.unescape(text)
    decoded = _INVISIBLE.sub("", decoded).replace("\u00a0", " ")
    return decoded.strip()
