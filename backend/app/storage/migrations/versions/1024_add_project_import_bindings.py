"""add project import bindings

Revision ID: 1024
Revises: 1023
Create Date: 2026-08-25 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1024"
down_revision: str | Sequence[str] | None = "1023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_import_bindings",
        sa.Column("id", sa.String(length=21), nullable=False),
        sa.Column("project_id", sa.String(length=21), nullable=False),
        sa.Column("binding_key", sa.String(length=64), nullable=False),
        sa.Column("rule_id", sa.String(length=200), nullable=False),
        sa.Column("source_path", sa.String(length=1000), nullable=False),
        sa.Column("source_anchor", sa.String(length=2000), nullable=False),
        sa.Column("target_kind", sa.String(length=30), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("last_applied_hash", sa.String(length=71), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "target_kind IN ('world_entry', 'character', 'note', "
            "'note_category', 'discussion', 'discussion_message')",
            name="ck_project_import_bindings_target_kind",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_import_bindings_project_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "binding_key",
            name="uq_project_import_bindings_project_key",
        ),
        sa.UniqueConstraint(
            "project_id",
            "target_kind",
            "target_id",
            name="uq_project_import_bindings_project_target",
        ),
    )
    op.create_index(
        "ix_project_import_bindings_project_id",
        "project_import_bindings",
        ["project_id"],
    )
    op.create_index(
        "ix_project_import_bindings_project_source",
        "project_import_bindings",
        ["project_id", "rule_id", "source_path"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_import_bindings_project_source",
        table_name="project_import_bindings",
    )
    op.drop_index(
        "ix_project_import_bindings_project_id",
        table_name="project_import_bindings",
    )
    op.drop_table("project_import_bindings")
