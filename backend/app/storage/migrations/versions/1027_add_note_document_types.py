"""add note document types

Revision ID: 1027
Revises: 1026
Create Date: 2026-08-26 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1027"
down_revision: str | Sequence[str] | None = "1026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name in ("notes", "note_categories"):
        op.add_column(
            table_name,
            sa.Column(
                "document_type",
                sa.String(length=20),
                nullable=False,
                server_default="note",
            ),
        )
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_check_constraint(
                f"ck_{table_name}_document_type",
                "document_type IN ('note', 'outline')",
            )
            batch_op.alter_column("document_type", server_default=None)
        op.create_index(
            f"ix_{table_name}_document_type",
            table_name,
            ["document_type"],
        )


def downgrade() -> None:
    for table_name in ("note_categories", "notes"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(
                f"ck_{table_name}_document_type",
                type_="check",
            )
        op.drop_index(f"ix_{table_name}_document_type", table_name=table_name)
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column("document_type")
