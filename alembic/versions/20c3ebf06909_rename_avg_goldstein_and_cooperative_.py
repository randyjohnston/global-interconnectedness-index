"""rename avg_goldstein and cooperative_ratio with geopolitics prefix

Revision ID: 20c3ebf06909
Revises: c38ef2975cfe
Create Date: 2026-04-21 11:05:37.991297

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20c3ebf06909'
down_revision: Union[str, None] = 'c38ef2975cfe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('index_snapshots', 'avg_goldstein', new_column_name='geopolitics_avg_goldstein')
    op.alter_column('index_snapshots', 'cooperative_ratio', new_column_name='geopolitics_cooperative_ratio')


def downgrade() -> None:
    op.alter_column('index_snapshots', 'geopolitics_avg_goldstein', new_column_name='avg_goldstein')
    op.alter_column('index_snapshots', 'geopolitics_cooperative_ratio', new_column_name='cooperative_ratio')
