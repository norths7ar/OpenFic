"""add project import profiles

Revision ID: 1030
Revises: 1029
Create Date: 2026-08-27 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1030"
down_revision: str | Sequence[str] | None = "1029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_import_profiles",
        sa.Column("project_id", sa.String(length=21), nullable=False),
        sa.Column("mapping_yaml", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_import_profiles_project_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("project_id"),
    )


def downgrade() -> None:
    op.drop_table("project_import_profiles")
