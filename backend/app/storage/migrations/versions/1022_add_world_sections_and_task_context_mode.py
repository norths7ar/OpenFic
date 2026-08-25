"""add world entry sections and task context mode.

Revision ID: 1022
Revises: 1021
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1022"
down_revision: str | Sequence[str] | None = "1021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "world_info_entries",
        sa.Column("section", sa.String(length=500), nullable=False, server_default=""),
    )
    op.add_column(
        "revision_world_entry_snapshots",
        sa.Column("section", sa.String(length=500), nullable=True),
    )
    with op.batch_alter_table("world_info_entries") as batch_op:
        batch_op.alter_column("section", server_default=None)

    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(
            sa.Column(
                "context_mode",
                sa.String(length=20),
                nullable=False,
                server_default="local",
            )
        )
        batch_op.create_check_constraint(
            "ck_tasks_context_mode", "context_mode IN ('global', 'local')"
        )

    with op.batch_alter_table("tasks") as batch_op:
        batch_op.alter_column("context_mode", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_constraint("ck_tasks_context_mode", type_="check")
        batch_op.drop_column("context_mode")
    op.drop_column("revision_world_entry_snapshots", "section")
    op.drop_column("world_info_entries", "section")
