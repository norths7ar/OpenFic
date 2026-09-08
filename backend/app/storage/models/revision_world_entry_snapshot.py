"""Materialized world-entry snapshots for a revision."""

from datetime import UTC, datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.core.ids import generate_id
from app.storage.models.agent_visibility import AgentVisibilitySnapshotModel


class RevisionWorldEntrySnapshot(AgentVisibilitySnapshotModel, table=True):
    """World entry state before a revision's change, used for rollback."""

    __tablename__ = "revision_world_entry_snapshots"
    __table_args__ = (
        UniqueConstraint("revision_id", "entry_id", name="uq_revision_world_entry_snapshot"),
    )

    id: str = Field(default_factory=generate_id, primary_key=True)
    revision_id: str = Field(index=True, foreign_key="revisions.id")
    entry_id: str = Field(index=True)
    project_id: str = Field(index=True, foreign_key="projects.id")
    exists: bool = Field(default=True)
    world_info_id: str | None = Field(default=None, index=True)
    uid: int | None = Field(default=None, index=True)
    name: str | None = Field(default=None, max_length=200)
    section: str | None = Field(default=None, max_length=500)
    entry_order: int | None = Field(default=None, index=True)
    content: str | None = Field(default=None)
    content_blob_id: str | None = Field(
        default=None,
        description="正文的内容寻址 blob id(长文本时使用)",
    )
    token_count: int | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
