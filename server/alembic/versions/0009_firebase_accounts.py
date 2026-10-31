"""Firebase accounts for LAN worlds

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-31 20:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('firebase_uid', sa.String(length=128), nullable=True))
        batch.add_column(sa.Column('email', sa.String(length=200), nullable=True))
        batch.create_index('ix_users_firebase_uid', ['firebase_uid'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.drop_index('ix_users_firebase_uid')
        batch.drop_column('email')
        batch.drop_column('firebase_uid')
