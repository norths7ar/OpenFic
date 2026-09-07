"""Use project folders for writing, outlines and notes; preserve entity IDs."""

import sqlalchemy as sa
from alembic import op

revision = "1034"
down_revision = "1033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.execute(
        sa.text("SELECT COUNT(*) FROM note_categories WHERE parent_id IS NOT NULL")
    ).scalar_one():
        raise RuntimeError("Expected flat note categories after migration 1031")
    # Never rename or merge records to satisfy a name constraint. IDs are identity.
    with op.batch_alter_table("project_folders") as batch:
        batch.drop_constraint("uq_project_folders_project_scope_title", type_="unique")
        batch.add_column(sa.Column("description", sa.Text(), nullable=True))
        batch.add_column(sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"))
    bind.execute(
        sa.text("""
        INSERT INTO project_folders (id, project_id, scope, title, description, "order", item_count, created_at, updated_at)
        SELECT id, project_id, 'writing', title, description, "order", chapter_count, created_at, updated_at FROM volumes
    """)
    )
    bind.execute(
        sa.text("""
        INSERT INTO project_folders (id, project_id, scope, title, description, "order", item_count, created_at, updated_at)
        SELECT id, project_id, document_type, title, NULL, "order", 0, created_at, updated_at FROM note_categories
    """)
    )
    convention = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
    for table, column, old_table in [
        ("chapters", "volume_id", "volumes"),
        ("chapter_summaries", "volume_id", "volumes"),
        ("notes", "category_id", "note_categories"),
    ]:
        old_fk = next(
            fk
            for fk in sa.inspect(bind).get_foreign_keys(table)
            if fk["constrained_columns"] == [column]
        )
        name = old_fk["name"] or f"fk_{table}_{column}_{old_table}"
        with op.batch_alter_table(table, naming_convention=convention) as batch:
            batch.drop_constraint(name, type_="foreignkey")
            batch.alter_column(column, existing_type=sa.String(), nullable=True)
            batch.create_foreign_key(
                f"fk_{table}_{column}_project_folders",
                "project_folders",
                [column],
                ["id"],
                ondelete="SET NULL",
            )
    op.add_column(
        "revision_note_snapshots",
        sa.Column("document_type", sa.String(), nullable=False, server_default="note"),
    )
    op.add_column(
        "revision_note_category_snapshots",
        sa.Column("scope", sa.String(), nullable=False, server_default="note"),
    )
    op.add_column(
        "revision_note_category_snapshots", sa.Column("description", sa.Text(), nullable=True)
    )
    bind.execute(
        sa.text(
            "UPDATE revision_note_snapshots SET document_type = COALESCE((SELECT document_type FROM notes WHERE notes.id = note_id), 'note')"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE revision_note_category_snapshots SET scope = COALESCE((SELECT document_type FROM note_categories WHERE note_categories.id = category_id), 'note')"
        )
    )
    op.drop_table("note_categories")
    op.drop_table("volumes")


def downgrade() -> None:
    raise RuntimeError(
        "Restore the pre-upgrade backup; root chapters and duplicate folder names cannot be represented by the old schema"
    )
