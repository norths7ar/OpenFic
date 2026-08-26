"""add model enabled state

Revision ID: 1028
Revises: 1027
Create Date: 2026-08-26 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1028"
down_revision: str | Sequence[str] | None = "1027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "models",
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_models_is_enabled", "models", ["is_enabled"])
    with op.batch_alter_table("models") as batch_op:
        batch_op.alter_column("is_enabled", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_models_is_enabled", table_name="models")
    with op.batch_alter_table("models") as batch_op:
        batch_op.drop_column("is_enabled")
