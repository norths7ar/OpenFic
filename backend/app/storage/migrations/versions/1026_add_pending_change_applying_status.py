"""add pending change applying status

Revision ID: 1026
Revises: 1025
Create Date: 2026-08-25 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "1026"
down_revision: str | Sequence[str] | None = "1025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("pending_project_changes") as batch_op:
        batch_op.drop_constraint(
            "ck_pending_project_changes_status",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_pending_project_changes_status",
            "status IN ('pending', 'applying', 'rejected', 'applied')",
        )


def downgrade() -> None:
    with op.batch_alter_table("pending_project_changes") as batch_op:
        batch_op.drop_constraint(
            "ck_pending_project_changes_status",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_pending_project_changes_status",
            "status IN ('pending', 'rejected', 'applied')",
        )
