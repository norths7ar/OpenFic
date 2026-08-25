"""add manual order and writing visibility to project knowledge.

Revision ID: 1021
Revises: 1020
Create Date: 2026-08-25 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1021"
down_revision: str | Sequence[str] | None = "1020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _backfill_order(
    table_name: str,
    columns: dict[str, sa.types.TypeEngine],
    group_columns: tuple[str, ...],
    order_columns: tuple[sa.ColumnElement, ...],
) -> None:
    table = sa.table(
        table_name,
        *[sa.column(name, column_type) for name, column_type in columns.items()],
    )
    connection = op.get_bind()
    rows = (
        connection.execute(
            sa.select(table).order_by(
                *[table.c[name] for name in group_columns], *order_columns
            )
        )
        .mappings()
        .all()
    )
    counters: dict[tuple[object, ...], int] = {}
    for row in rows:
        group = tuple(row[name] for name in group_columns)
        counters[group] = counters.get(group, 0) + 1
        connection.execute(
            table.update().where(table.c.id == row["id"]).values(order=counters[group])
        )


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "characters",
        sa.Column(
            "is_writing_visible", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    op.add_column(
        "notes", sa.Column("order", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "notes",
        sa.Column(
            "is_writing_visible", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    op.add_column(
        "note_categories",
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
    )

    _backfill_order(
        "characters",
        {
            "id": sa.String(),
            "project_id": sa.String(),
            "is_favorited": sa.Boolean(),
            "updated_at": sa.DateTime(),
            "order": sa.Integer(),
        },
        ("project_id",),
        (
            sa.column("is_favorited").desc(),
            sa.column("updated_at").desc(),
            sa.column("id").asc(),
        ),
    )
    _backfill_order(
        "notes",
        {
            "id": sa.String(),
            "project_id": sa.String(),
            "category_id": sa.String(),
            "title": sa.String(),
            "order": sa.Integer(),
        },
        ("project_id", "category_id"),
        (sa.column("title").asc(), sa.column("id").asc()),
    )
    _backfill_order(
        "note_categories",
        {
            "id": sa.String(),
            "project_id": sa.String(),
            "parent_id": sa.String(),
            "title": sa.String(),
            "order": sa.Integer(),
        },
        ("project_id", "parent_id"),
        (sa.column("title").asc(), sa.column("id").asc()),
    )

    for table_name, column in (
        ("characters", "order"),
        ("characters", "is_writing_visible"),
        ("notes", "order"),
        ("notes", "is_writing_visible"),
        ("note_categories", "order"),
    ):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(column, server_default=None)

    op.create_index("ix_characters_order", "characters", ["order"])
    op.create_index(
        "ix_characters_is_writing_visible",
        "characters",
        ["is_writing_visible"],
    )
    op.create_index("ix_notes_order", "notes", ["order"])
    op.create_index(
        "ix_notes_is_writing_visible",
        "notes",
        ["is_writing_visible"],
    )
    op.create_index("ix_note_categories_order", "note_categories", ["order"])

    op.add_column(
        "revision_character_snapshots",
        sa.Column("character_order", sa.Integer(), nullable=True),
    )
    op.add_column(
        "revision_character_snapshots",
        sa.Column("is_writing_visible", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "revision_note_snapshots", sa.Column("note_order", sa.Integer(), nullable=True)
    )
    op.add_column(
        "revision_note_snapshots",
        sa.Column("is_writing_visible", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "revision_note_category_snapshots",
        sa.Column("category_order", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("revision_note_category_snapshots", "category_order")
    op.drop_column("revision_note_snapshots", "is_writing_visible")
    op.drop_column("revision_note_snapshots", "note_order")
    op.drop_column("revision_character_snapshots", "is_writing_visible")
    op.drop_column("revision_character_snapshots", "character_order")
    op.drop_index("ix_note_categories_order", table_name="note_categories")
    op.drop_index("ix_notes_is_writing_visible", table_name="notes")
    op.drop_index("ix_notes_order", table_name="notes")
    op.drop_index("ix_characters_is_writing_visible", table_name="characters")
    op.drop_index("ix_characters_order", table_name="characters")
    with op.batch_alter_table("note_categories") as batch_op:
        batch_op.drop_column("order")
    with op.batch_alter_table("notes") as batch_op:
        batch_op.drop_column("is_writing_visible")
        batch_op.drop_column("order")
    with op.batch_alter_table("characters") as batch_op:
        batch_op.drop_column("is_writing_visible")
        batch_op.drop_column("order")
