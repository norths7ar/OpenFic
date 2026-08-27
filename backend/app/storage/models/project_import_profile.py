"""Project-level Markdown source mapping saved after a successful import."""

from datetime import UTC, datetime

from sqlalchemy import Column, ForeignKey, String, Text
from sqlmodel import Field, SQLModel


class ProjectImportProfile(SQLModel, table=True):
    """Store the active source-map YAML for one project."""

    __tablename__ = "project_import_profiles"

    project_id: str = Field(
        sa_column=Column(
            String(21),
            ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
    )
    mapping_yaml: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
