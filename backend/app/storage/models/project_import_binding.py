"""Persistent baselines for declarative project document imports."""

from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel

from app.core.ids import generate_id


class ProjectImportBinding(SQLModel, table=True):
    """Bind one stable source object to one OpenFic object and applied hash."""

    __tablename__ = "project_import_bindings"
    __table_args__ = (
        CheckConstraint(
            "target_kind IN ('world_entry', 'character', 'note', "
            "'note_category', 'project_folder', 'discussion', 'discussion_message')",
            name="ck_project_import_bindings_target_kind",
        ),
        UniqueConstraint(
            "project_id",
            "binding_key",
            name="uq_project_import_bindings_project_key",
        ),
        UniqueConstraint(
            "project_id",
            "target_kind",
            "target_id",
            name="uq_project_import_bindings_project_target",
        ),
        Index(
            "ix_project_import_bindings_project_source",
            "project_id",
            "rule_id",
            "source_path",
        ),
    )

    id: str = Field(default_factory=generate_id, primary_key=True)
    project_id: str = Field(
        sa_column=Column(
            String(21),
            ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    binding_key: str = Field(max_length=64)
    rule_id: str = Field(max_length=200)
    source_path: str = Field(max_length=1000)
    source_anchor: str = Field(max_length=2000)
    target_kind: str = Field(max_length=30)
    target_id: str = Field(max_length=64)
    last_applied_hash: str = Field(max_length=71)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
