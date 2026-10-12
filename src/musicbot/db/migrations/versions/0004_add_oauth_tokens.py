"""add oauth tokens

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-13 01:16:08.668467
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_tokens",
        sa.Column("service", sa.String(length=32), nullable=False),
        sa.Column("access_token", sa.String(length=1024), nullable=False),
        sa.Column("refresh_token", sa.String(length=1024), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
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
        sa.PrimaryKeyConstraint("service", name=op.f("pk_oauth_tokens")),
    )


def downgrade() -> None:
    op.drop_table("oauth_tokens")
