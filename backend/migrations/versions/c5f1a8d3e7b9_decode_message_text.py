"""Decode the HTML entities in stored buyer messages

Revision ID: c5f1a8d3e7b9
Revises: b8e3d5a7c246
Create Date: 2026-09-24

Allegro's Message Center hands messages over as HTML text (`zam&oacute;wienie`,
`&quot;`, a `&zwnj;` between paragraphs), which the first syncs stored as they
came. The mapper now decodes them (`app/core/text.py`); this cleans what is
already stored, and rebuilds each thread's excerpt from its newest message.

"""

import html
import re
from collections import defaultdict
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5f1a8d3e7b9"
down_revision: str | Sequence[str] | None = "b8e3d5a7c246"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# kept in step with app/core/text.py by hand: a migration must not change when
# the application's code does
_INVISIBLE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
EXCERPT_LENGTH = 500


def _clean(text: str) -> str:
    return _INVISIBLE.sub("", html.unescape(text)).replace("\u00a0", " ").strip()


def upgrade() -> None:
    bind = op.get_bind()
    messages = sa.table(
        "messages",
        sa.column("id", sa.Uuid()),
        sa.column("thread_id", sa.Uuid()),
        sa.column("text", sa.Text()),
        sa.column("sent_at", sa.DateTime(timezone=True)),
    )
    threads = sa.table(
        "message_threads",
        sa.column("id", sa.Uuid()),
        sa.column("last_message_text", sa.String(500)),
    )

    newest: dict = {}
    for row in bind.execute(
        sa.select(messages.c.id, messages.c.thread_id, messages.c.text, messages.c.sent_at)
    ):
        cleaned = _clean(row.text or "")
        if cleaned != (row.text or ""):
            bind.execute(
                sa.update(messages).where(messages.c.id == row.id).values(text=cleaned)
            )
        best = newest.get(row.thread_id)
        if best is None or row.sent_at >= best[0]:
            newest[row.thread_id] = (row.sent_at, cleaned)

    by_thread: dict = defaultdict(str)
    for thread_id, (_, text) in newest.items():
        by_thread[thread_id] = text[:EXCERPT_LENGTH]
    for thread_id, excerpt in by_thread.items():
        bind.execute(
            sa.update(threads).where(threads.c.id == thread_id).values(last_message_text=excerpt)
        )


def downgrade() -> None:
    # decoding loses which characters were written as entities: nothing to undo
    pass
