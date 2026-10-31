"""Bí cảnh members and loot claims (stage 9)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-31 10:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'realm_members',
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('realm_id', sa.String(length=32), nullable=False),
        sa.Column('day', sa.String(length=10), nullable=False),
        sa.Column('joined_at', sa.DateTime(), nullable=False),
        sa.Column('left_at', sa.DateTime(), nullable=True),
        sa.Column('result', sa.String(length=12), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['realm_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('run_id', 'user_id'),
    )
    op.create_index('ix_realm_members_user_day', 'realm_members', ['user_id', 'day'])
    op.create_table(
        'realm_claims',
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('stage', sa.String(length=16), nullable=False),
        sa.Column('loot', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['realm_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('run_id', 'user_id', 'stage'),
    )


def downgrade() -> None:
    op.drop_table('realm_claims')
    op.drop_index('ix_realm_members_user_day', table_name='realm_members')
    op.drop_table('realm_members')
