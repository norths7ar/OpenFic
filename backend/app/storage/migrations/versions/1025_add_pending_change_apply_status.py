"""add pending change apply status

Revision ID: 1025
Revises: 1024
Create Date: 2026-08-25 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1025"
down_revision: str | Sequence[str] | None = "1024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pending_project_changes",
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    with op.batch_alter_table("pending_project_changes") as batch_op:
        batch_op.drop_constraint(
            "ck_pending_project_changes_status",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_pending_project_changes_status",
            "status IN ('pending', 'rejected', 'applied')",
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE pending_project_changes "
            "SET status = 'rejected' WHERE status = 'applied'"
        )
    )
    with op.batch_alter_table("pending_project_changes") as batch_op:
        batch_op.drop_constraint(
            "ck_pending_project_changes_status",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_pending_project_changes_status",
            "status IN ('pending', 'rejected')",
        )
        batch_op.drop_column("applied_at")
