"""add cached tracks

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-12 23:20:41.512350
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cached_tracks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("audio_format", sa.String(length=8), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("artist", sa.String(length=255), nullable=False),
        sa.Column("file_id", sa.String(length=255), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cached_tracks")),
        sa.UniqueConstraint(
            "source", "source_id", "audio_format", name=op.f("uq_cached_tracks_track")
        ),
    )


def downgrade() -> None:
    op.drop_table("cached_tracks")
