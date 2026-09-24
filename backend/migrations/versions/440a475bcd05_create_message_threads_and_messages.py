"""Create message_threads and messages (buyer messages, plan B2)

Revision ID: 440a475bcd05
Revises: f5c3b8e1d726
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "440a475bcd05"
down_revision: str | Sequence[str] | None = "f5c3b8e1d726"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "message_threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "source",
            sa.Enum("ALLEGRO", "ERLI", name="ordersource", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("interlocutor_login", sa.String(length=255), nullable=True),
        sa.Column("order_external_id", sa.String(length=255), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_text", sa.String(length=500), nullable=True),
        sa.Column("read", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("aside", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_id", name="uq_message_threads_source_external_id"),
    )
    op.create_index(
        op.f("ix_message_threads_order_external_id"),
        "message_threads",
        ["order_external_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_message_threads_last_message_at"),
        "message_threads",
        ["last_message_at"],
        unique=False,
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column(
            "direction",
            sa.Enum("IN", "OUT", name="messagedirection", native_enum=False, length=8),
            nullable=False,
        ),
        sa.Column("author_login", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_in_anvero", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["message_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id", "external_id", name="uq_messages_thread_id_external_id"),
    )
    op.create_index(op.f("ix_messages_thread_id"), "messages", ["thread_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_messages_thread_id"), table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_message_threads_last_message_at"), table_name="message_threads")
    op.drop_index(op.f("ix_message_threads_order_external_id"), table_name="message_threads")
    op.drop_table("message_threads")
