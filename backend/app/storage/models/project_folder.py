"""Single-level folders shared by project navigation pages."""

from datetime import UTC, datetime

from sqlalchemy import Column, ForeignKey, String
from sqlmodel import Field, SQLModel

from app.core.ids import generate_id


class ProjectFolder(SQLModel, table=True):
    __tablename__ = "project_folders"

    id: str = Field(default_factory=generate_id, primary_key=True)
    project_id: str = Field(
        sa_column=Column(
            String(21),
            ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    scope: str = Field(max_length=20, index=True)
    title: str = Field(max_length=200)
    description: str | None = Field(default=None)
    item_count: int = Field(default=0)
    order: int = Field(default=0, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
