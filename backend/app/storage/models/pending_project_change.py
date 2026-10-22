"""待审项目变更数据模型。"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DDL, JSON, CheckConstraint, Column, Index, event
from sqlmodel import Field, SQLModel

from app.core.ids import generate_id


class PendingProjectChange(SQLModel, table=True):
    """尚未应用到项目正式资料的候审变更。"""

    __tablename__ = "pending_project_changes"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('create', 'update', 'delete')",
            name="ck_pending_project_changes_operation",
        ),
        CheckConstraint(
            "status IN ('pending', 'applying', 'rejected', 'applied')",
            name="ck_pending_project_changes_status",
        ),
        Index(
            "ix_pending_project_changes_project_status_created_at",
            "project_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_pending_project_changes_project_target",
            "project_id",
            "target_type",
            "target_id",
        ),
    )

    id: str = Field(default_factory=generate_id, primary_key=True)
    project_id: str = Field(index=True, foreign_key="projects.id")
    target_type: str = Field(max_length=100)
    target_id: str | None = Field(default=None, max_length=200)
    operation: str = Field(max_length=20)
    base_hash: str | None = Field(default=None, max_length=128)
    before: Any = Field(default=None, sa_column=Column(JSON, nullable=True))
    after: Any = Field(default=None, sa_column=Column(JSON, nullable=True))
    current_revision_id: str | None = Field(default=None)
    applied_revision_id: str | None = Field(default=None)
    source_task_id: str | None = Field(default=None, max_length=128, index=True)
    source_message_id: str | None = Field(default=None, max_length=128, index=True)
    model_id: str | None = Field(default=None, max_length=200, index=True)
    status: str = Field(default="pending", max_length=20)
    applied_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PendingProjectChangeRevision(SQLModel, table=True):
    """An immutable, complete proposed result, including null for deletion."""

    __tablename__ = "pending_project_change_revisions"
    __table_args__ = (
        CheckConstraint(
            "source IN ('manual', 'ai', 'migration')", name="ck_pending_change_revision_source"
        ),
    )

    id: str = Field(default_factory=generate_id, primary_key=True)
    change_id: str = Field(foreign_key="pending_project_changes.id", ondelete="CASCADE", index=True)
    after: Any = Field(default=None, sa_column=Column(JSON, nullable=True))
    source: str = Field(max_length=20)
    source_task_id: str | None = Field(default=None, max_length=128)
    source_message_id: str | None = Field(default=None, max_length=128)
    model_id: str | None = Field(default=None, max_length=200)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


event.listen(
    SQLModel.metadata.tables["pending_project_change_revisions"],
    "after_create",
    DDL("""CREATE TRIGGER pending_change_revision_immutable
    BEFORE UPDATE ON pending_project_change_revisions
    BEGIN SELECT RAISE(ABORT, 'proposal revisions are immutable'); END"""),
)
event.listen(
    SQLModel.metadata.tables["pending_project_change_revisions"],
    "after_create",
    DDL("""CREATE TRIGGER pending_change_revision_cleanup
    AFTER DELETE ON pending_project_changes
    BEGIN DELETE FROM pending_project_change_revisions WHERE change_id=OLD.id; END"""),
)
