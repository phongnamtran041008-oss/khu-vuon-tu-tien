"""garden depth and character

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-29 23:39:48.509854
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('characters', schema=None) as batch_op:
        batch_op.add_column(sa.Column('facing', sa.String(length=5), nullable=False, server_default='down'))
    with op.batch_alter_table('plots', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fire_checked_date', sa.String(length=10), nullable=True))
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('flags', sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('flags')
    with op.batch_alter_table('plots', schema=None) as batch_op:
        batch_op.drop_column('fire_checked_date')
    with op.batch_alter_table('characters', schema=None) as batch_op:
        batch_op.drop_column('facing')
