"""add pending project changes

Revision ID: 1020
Revises: 1019
Create Date: 2026-08-24 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1020"
down_revision: str | Sequence[str] | None = "1019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pending_project_changes",
        sa.Column("id", sa.String(length=21), nullable=False),
        sa.Column("project_id", sa.String(length=21), nullable=False),
        sa.Column("target_type", sa.String(length=100), nullable=False),
        sa.Column("target_id", sa.String(length=200), nullable=True),
        sa.Column("operation", sa.String(length=20), nullable=False),
        sa.Column("base_hash", sa.String(length=128), nullable=True),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("source_task_id", sa.String(length=128), nullable=True),
        sa.Column("source_message_id", sa.String(length=128), nullable=True),
        sa.Column("model_id", sa.String(length=200), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "operation IN ('create', 'update', 'delete')",
            name="ck_pending_project_changes_operation",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'rejected')",
            name="ck_pending_project_changes_status",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_pending_project_changes_project_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pending_project_changes_project_id",
        "pending_project_changes",
        ["project_id"],
    )
    op.create_index(
        "ix_pending_project_changes_project_status_created_at",
        "pending_project_changes",
        ["project_id", "status", "created_at"],
    )
    op.create_index(
        "ix_pending_project_changes_project_target",
        "pending_project_changes",
        ["project_id", "target_type", "target_id"],
    )
    op.create_index(
        "ix_pending_project_changes_source_task_id",
        "pending_project_changes",
        ["source_task_id"],
    )
    op.create_index(
        "ix_pending_project_changes_source_message_id",
        "pending_project_changes",
        ["source_message_id"],
    )
    op.create_index(
        "ix_pending_project_changes_model_id",
        "pending_project_changes",
        ["model_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pending_project_changes_model_id",
        table_name="pending_project_changes",
    )
    op.drop_index(
        "ix_pending_project_changes_source_message_id",
        table_name="pending_project_changes",
    )
    op.drop_index(
        "ix_pending_project_changes_source_task_id",
        table_name="pending_project_changes",
    )
    op.drop_index(
        "ix_pending_project_changes_project_target",
        table_name="pending_project_changes",
    )
    op.drop_index(
        "ix_pending_project_changes_project_status_created_at",
        table_name="pending_project_changes",
    )
    op.drop_index(
        "ix_pending_project_changes_project_id",
        table_name="pending_project_changes",
    )
    op.drop_table("pending_project_changes")
