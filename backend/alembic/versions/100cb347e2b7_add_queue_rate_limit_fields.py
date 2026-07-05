"""add_queue_rate_limit_fields

Revision ID: 100cb347e2b7
Revises: 4fc2ad3f8218
Create Date: 2026-07-05 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '100cb347e2b7'
down_revision: Union[str, None] = '4fc2ad3f8218'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('queues', sa.Column('rate_limit_per_minute', sa.Integer(), nullable=True))
    op.add_column('queues', sa.Column('rate_limit_burst', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('queues', 'rate_limit_burst')
    op.drop_column('queues', 'rate_limit_per_minute')
