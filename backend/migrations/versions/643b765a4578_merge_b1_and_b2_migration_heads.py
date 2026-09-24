"""merge B1 and B2 migration heads

Revision ID: 643b765a4578
Revises: 440a475bcd05, d2f7b3e9a614
Create Date: 2026-09-24 12:53:12.385696

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '643b765a4578'
down_revision: Union[str, Sequence[str], None] = ('440a475bcd05', 'd2f7b3e9a614')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
