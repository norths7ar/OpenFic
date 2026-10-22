"""Preserve known proposal results without inventing earlier revision history."""

import sqlalchemy as sa
from alembic import op

revision = "20261020"
down_revision = "20260909"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("pending_project_changes", sa.Column("current_revision_id", sa.String()))
    op.add_column("pending_project_changes", sa.Column("applied_revision_id", sa.String()))
    op.create_table(
        "pending_project_change_revisions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "change_id",
            sa.String(),
            sa.ForeignKey("pending_project_changes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("source_task_id", sa.String(128)),
        sa.Column("source_message_id", sa.String(128)),
        sa.Column("model_id", sa.String(200)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "source IN ('manual', 'ai', 'migration')", name="ck_pending_change_revision_source"
        ),
    )
    op.create_index(
        "ix_pending_project_change_revisions_change_id",
        "pending_project_change_revisions",
        ["change_id"],
    )
    # The only recoverable right-hand value is the stored after. Its provenance
    # is unknown, even when the proposal itself originally came from an agent.
    # Do not infer applied_revision_id for already-applied legacy proposals.
    op.execute("""INSERT INTO pending_project_change_revisions
        (id, change_id, after, source, created_at)
        SELECT 'migration_' || id, id, after, 'migration', strftime('%Y-%m-%d %H:%M:%f','now')
        FROM pending_project_changes""")
    op.execute("""UPDATE pending_project_changes
        SET current_revision_id = 'migration_' || id""")
    op.execute("""CREATE TRIGGER pending_change_revision_immutable
        BEFORE UPDATE ON pending_project_change_revisions
        BEGIN SELECT RAISE(ABORT, 'proposal revisions are immutable'); END""")
    op.execute("""CREATE TRIGGER pending_change_revision_cleanup
        AFTER DELETE ON pending_project_changes
        BEGIN DELETE FROM pending_project_change_revisions WHERE change_id=OLD.id; END""")


def downgrade():
    op.execute("DROP TRIGGER pending_change_revision_immutable")
    op.execute("DROP TRIGGER pending_change_revision_cleanup")
    op.drop_table("pending_project_change_revisions")
    op.drop_column("pending_project_changes", "applied_revision_id")
    op.drop_column("pending_project_changes", "current_revision_id")
