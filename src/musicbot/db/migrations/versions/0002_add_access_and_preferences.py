"""add access and preferences

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-12 22:54:24.287820
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_allowed", sa.Boolean(), server_default=sa.text("0"), nullable=False)
        )
        batch_op.add_column(sa.Column("access_requested_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("audio_format", sa.String(length=8), server_default="m4a", nullable=False)
        )
        batch_op.add_column(sa.Column("channel_id", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("channel_title", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("channel_title")
        batch_op.drop_column("channel_id")
        batch_op.drop_column("audio_format")
        batch_op.drop_column("access_requested_at")
        batch_op.drop_column("is_allowed")
