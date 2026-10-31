"""Admin action log (stage 10)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-31 18:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'admin_actions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('admin_name', sa.String(length=40), nullable=False),
        sa.Column('action', sa.String(length=20), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('target_name', sa.String(length=40), nullable=True),
        sa.Column('detail', sa.String(length=300), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_admin_actions_action', 'admin_actions', ['action'])
    op.create_index('ix_admin_actions_target_id', 'admin_actions', ['target_id'])


def downgrade() -> None:
    op.drop_index('ix_admin_actions_target_id', table_name='admin_actions')
    op.drop_index('ix_admin_actions_action', table_name='admin_actions')
    op.drop_table('admin_actions')
