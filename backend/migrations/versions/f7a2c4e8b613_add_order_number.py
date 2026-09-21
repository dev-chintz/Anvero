"""Add orders.order_number: Anvero's own continuous order number

Revision ID: f7a2c4e8b613
Revises: e6c1d9a4f725
Create Date: 2026-09-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7a2c4e8b613"
down_revision: str | Sequence[str] | None = "e6c1d9a4f725"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    counters = op.create_table(
        "counters",
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )

    # nullable first, so existing rows can be numbered before the constraint
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(sa.Column("order_number", sa.Integer(), nullable=True))

    # existing orders are numbered oldest purchase first, so the numbers read
    # in the order the orders were placed; ties fall back to when the row was
    # created, then to the id, so the result does not depend on the database
    connection = op.get_bind()
    orders = sa.table(
        "orders",
        sa.column("id", sa.Uuid()),
        sa.column("ordered_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("order_number", sa.Integer()),
    )
    rows = connection.execute(
        sa.select(orders.c.id).order_by(orders.c.ordered_at, orders.c.created_at, orders.c.id)
    ).all()
    for number, (order_id,) in enumerate(rows, start=1):
        connection.execute(
            orders.update().where(orders.c.id == order_id).values(order_number=number)
        )
    op.bulk_insert(counters, [{"name": "order_number", "value": len(rows)}])

    with op.batch_alter_table("orders") as batch_op:
        batch_op.alter_column("order_number", existing_type=sa.Integer(), nullable=False)
        batch_op.create_unique_constraint("uq_orders_order_number", ["order_number"])


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_constraint("uq_orders_order_number", type_="unique")
        batch_op.drop_column("order_number")
    op.drop_table("counters")
