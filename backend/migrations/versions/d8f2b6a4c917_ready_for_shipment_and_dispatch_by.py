"""Add the READY_FOR_SHIPMENT status and orders.dispatch_by

Revision ID: d8f2b6a4c917
Revises: c4e8a2f6d139
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8f2b6a4c917"
down_revision: str | Sequence[str] | None = "c4e8a2f6d139"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_VALUES = ("NEW", "CONFIRMED", "SHIPPED", "DELIVERED", "CANCELLED")
NEW_VALUES = ("NEW", "CONFIRMED", "READY_FOR_SHIPMENT", "SHIPPED", "DELIVERED", "CANCELLED")

# every column typed order_status
STATUS_COLUMNS = (
    ("orders", "status"),
    ("orders", "marketplace_status"),
    ("order_status_history", "from_status"),
    ("order_status_history", "to_status"),
)


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        # a value added to an enum type cannot be used in the transaction that
        # added it, and the data step below uses it, so commit it first
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'READY_FOR_SHIPMENT' "
                "AFTER 'CONFIRMED'"
            )
    else:
        # elsewhere the enum is a plain string column sized to its longest
        # value, which the new one outgrows
        _retype_string_columns(OLD_VALUES, NEW_VALUES)

    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(sa.Column("dispatch_by", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(op.f("ix_orders_dispatch_by"), ["dispatch_by"])

    # Orders Allegro already calls READY_FOR_SHIPMENT were stored as CONFIRMED.
    # The import moves the status only when the marketplace's does, so without
    # this they would stay CONFIRMED until Allegro changes them again. The
    # operator's own status moves only where it still matched Allegro's.
    op.execute(
        "UPDATE orders SET marketplace_status = 'READY_FOR_SHIPMENT' "
        "WHERE marketplace_status = 'CONFIRMED' "
        "AND marketplace_status_label = 'READY_FOR_SHIPMENT'"
    )
    op.execute(
        "UPDATE orders SET status = 'READY_FOR_SHIPMENT' "
        "WHERE status = 'CONFIRMED' AND marketplace_status = 'READY_FOR_SHIPMENT'"
    )


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_index(op.f("ix_orders_dispatch_by"))
        batch_op.drop_column("dispatch_by")

    for table, column in STATUS_COLUMNS:
        op.execute(
            f"UPDATE {table} SET {column} = 'CONFIRMED' WHERE {column} = 'READY_FOR_SHIPMENT'"
        )

    if op.get_bind().dialect.name == "postgresql":
        # PostgreSQL cannot drop a value from an enum type: build the old type
        # again and move every column over to it
        op.execute("ALTER TYPE order_status RENAME TO order_status_with_ready")
        values = ", ".join(f"'{v}'" for v in OLD_VALUES)
        op.execute(f"CREATE TYPE order_status AS ENUM ({values})")
        for table, column in STATUS_COLUMNS:
            op.execute(
                f"ALTER TABLE {table} ALTER COLUMN {column} TYPE order_status "
                f"USING {column}::text::order_status"
            )
        op.execute("DROP TYPE order_status_with_ready")
    else:
        _retype_string_columns(NEW_VALUES, OLD_VALUES)


def _retype_string_columns(old: tuple[str, ...], new: tuple[str, ...]) -> None:
    for table, column in STATUS_COLUMNS:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                column,
                existing_type=sa.Enum(*old, name="order_status"),
                type_=sa.Enum(*new, name="order_status"),
            )
