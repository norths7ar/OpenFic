"""allow project folder import bindings

Revision ID: 1033
Revises: 1032
Create Date: 2026-09-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "1033"
down_revision: str | Sequence[str] | None = "1032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = (
    "target_kind IN ('world_entry', 'character', 'note', "
    "'note_category', 'discussion', 'discussion_message')"
)
_NEW = (
    "target_kind IN ('world_entry', 'character', 'note', "
    "'note_category', 'project_folder', 'discussion', 'discussion_message')"
)


def _replace_constraint(expression: str) -> None:
    with op.batch_alter_table("project_import_bindings") as batch_op:
        batch_op.drop_constraint("ck_project_import_bindings_target_kind", type_="check")
        batch_op.create_check_constraint("ck_project_import_bindings_target_kind", expression)


def upgrade() -> None:
    _replace_constraint(_NEW)


def downgrade() -> None:
    _replace_constraint(_OLD)
