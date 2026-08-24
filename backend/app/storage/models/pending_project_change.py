"""待审项目变更数据模型。"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, Column, Index
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
            "status IN ('pending', 'rejected')",
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
    source_task_id: str | None = Field(default=None, max_length=128, index=True)
    source_message_id: str | None = Field(default=None, max_length=128, index=True)
    model_id: str | None = Field(default=None, max_length=200, index=True)
    status: str = Field(default="pending", max_length=20)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
