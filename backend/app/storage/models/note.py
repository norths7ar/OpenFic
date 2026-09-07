"""
Note 数据模型。
"""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from app.core.ids import generate_id


class Note(SQLModel, table=True):
    __tablename__ = "notes"

    id: str = Field(default_factory=generate_id, primary_key=True)
    project_id: str = Field(index=True, foreign_key="projects.id")
    category_id: str | None = Field(
        default=None,
        index=True,
        foreign_key="project_folders.id",
    )
    title: str = Field(max_length=200)
    document_type: str = Field(default="note", max_length=20, index=True)
    order: int = Field(default=0, index=True)
    content: str = Field(default="")
    is_locked: bool = Field(default=False)
    is_hidden: bool = Field(default=False)
    is_writing_visible: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
