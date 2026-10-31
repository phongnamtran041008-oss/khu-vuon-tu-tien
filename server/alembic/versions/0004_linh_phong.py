"""Linh Phong: hive honey/wax/cells, pollination boost, bee hatch time (stage 5)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-30 08:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('hive', schema=None) as batch_op:
        batch_op.add_column(sa.Column('honey', sa.Float(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('wax', sa.Float(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('cells', sa.Integer(), nullable=False, server_default='5'))
        batch_op.add_column(sa.Column('pollen_checked_at', sa.DateTime(), nullable=True))
    with op.batch_alter_table('plots', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pollen_boost', sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table('bees', schema=None) as batch_op:
        batch_op.add_column(sa.Column('obtained_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('bees', schema=None) as batch_op:
        batch_op.drop_column('obtained_at')
    with op.batch_alter_table('plots', schema=None) as batch_op:
        batch_op.drop_column('pollen_boost')
    with op.batch_alter_table('hive', schema=None) as batch_op:
        batch_op.drop_column('pollen_checked_at')
        batch_op.drop_column('cells')
        batch_op.drop_column('wax')
        batch_op.drop_column('honey')
