"""tribulation runs (stage 4)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-30 06:30:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tribulation_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('from_realm', sa.String(length=16), nullable=False),
        sa.Column('to_realm', sa.String(length=16), nullable=False),
        sa.Column('words', sa.JSON(), nullable=False),
        sa.Column('index', sa.Integer(), nullable=False),
        sa.Column('correct', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('result', sa.String(length=8), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_tribulation_runs_user_id', 'tribulation_runs', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_tribulation_runs_user_id', table_name='tribulation_runs')
    op.drop_table('tribulation_runs')
