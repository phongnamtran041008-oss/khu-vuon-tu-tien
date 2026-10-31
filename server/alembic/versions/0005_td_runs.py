"""Thủ Vườn runs in progress (stage 7)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-30 16:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'td_runs',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('level_id', sa.String(length=32), nullable=False),
        sa.Column('params', sa.JSON(), nullable=False),
        sa.Column('questions', sa.JSON(), nullable=False),
        sa.Column('events', sa.JSON(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_td_runs_user_id', 'td_runs', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_td_runs_user_id', table_name='td_runs')
    op.drop_table('td_runs')
