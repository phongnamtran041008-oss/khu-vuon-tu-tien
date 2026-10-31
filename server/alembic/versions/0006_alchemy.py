"""Luyện đan sessions (stage 8)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-30 23:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'alchemy_sessions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('recipe_id', sa.String(length=32), nullable=False),
        sa.Column('params', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_alchemy_sessions_user_id', 'alchemy_sessions', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_alchemy_sessions_user_id', table_name='alchemy_sessions')
    op.drop_table('alchemy_sessions')
