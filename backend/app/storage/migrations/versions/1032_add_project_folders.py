"""add shared single-level project folders

Revision ID: 1032
Revises: 1031
Create Date: 2026-09-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from app.core.ids import generate_id

revision: str = "1032"
down_revision: str | Sequence[str] | None = "1031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_folders",
        sa.Column("id", sa.String(length=21), nullable=False),
        sa.Column("project_id", sa.String(length=21), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "scope", "title", name="uq_project_folders_project_scope_title"
        ),
    )
    op.create_index("ix_project_folders_project_id", "project_folders", ["project_id"])
    op.create_index("ix_project_folders_scope", "project_folders", ["scope"])
    op.create_index("ix_project_folders_order", "project_folders", ["order"])

    for table_name in ("tasks", "characters", "world_info_entries"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(sa.Column("folder_id", sa.String(length=21), nullable=True))
            batch_op.create_index(f"ix_{table_name}_folder_id", ["folder_id"])
            batch_op.create_foreign_key(
                f"fk_{table_name}_folder_id_project_folders",
                "project_folders",
                ["folder_id"],
                ["id"],
                ondelete="SET NULL",
            )

    bind = op.get_bind()
    sections = list(
        bind.execute(
            sa.text(
                """
                SELECT wi.project_id, wie.section, MIN(wie."order") AS first_order
                FROM world_info_entries AS wie
                JOIN world_info AS wi ON wi.id = wie.world_info_id
                WHERE TRIM(wie.section) <> ''
                GROUP BY wi.project_id, wie.section
                ORDER BY wi.project_id, first_order, wie.section
                """
            )
        ).mappings()
    )
    next_order: dict[str, int] = {}
    now = datetime.now(UTC)
    for row in sections:
        project_id = str(row["project_id"])
        folder_id = generate_id()
        order = next_order.get(project_id, 0)
        next_order[project_id] = order + 1
        bind.execute(
            sa.text(
                """
                INSERT INTO project_folders
                    (id, project_id, scope, title, "order", created_at, updated_at)
                VALUES
                    (:id, :project_id, 'world', :title, :order, :created_at, :updated_at)
                """
            ),
            {
                "id": folder_id,
                "project_id": project_id,
                "title": str(row["section"]),
                "order": order,
                "created_at": now,
                "updated_at": now,
            },
        )
        bind.execute(
            sa.text(
                """
                UPDATE world_info_entries
                SET folder_id = :folder_id
                WHERE world_info_id IN (
                    SELECT id FROM world_info WHERE project_id = :project_id
                ) AND section = :title
                """
            ),
            {"folder_id": folder_id, "project_id": project_id, "title": str(row["section"])},
        )


def downgrade() -> None:
    for table_name in ("world_info_entries", "characters", "tasks"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(
                f"fk_{table_name}_folder_id_project_folders", type_="foreignkey"
            )
            batch_op.drop_index(f"ix_{table_name}_folder_id")
            batch_op.drop_column("folder_id")
    op.drop_index("ix_project_folders_order", table_name="project_folders")
    op.drop_index("ix_project_folders_scope", table_name="project_folders")
    op.drop_index("ix_project_folders_project_id", table_name="project_folders")
    op.drop_table("project_folders")
