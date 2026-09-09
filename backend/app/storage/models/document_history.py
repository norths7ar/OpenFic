"""Document recovery records, independent of agent tasks and revisions."""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from app.core.ids import generate_id


class DocumentHistory(SQLModel, table=True):
    __tablename__ = "document_history"

    id: str = Field(default_factory=generate_id, primary_key=True)
    project_id: str = Field(index=True)
    document_id: str = Field(index=True)
    kind: str
    title: str
    content: str
    source: str = "manual"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DocumentTrash(SQLModel, table=True):
    __tablename__ = "document_trash"

    id: str = Field(default_factory=generate_id, primary_key=True)
    project_id: str = Field(index=True)
    document_id: str = Field(index=True)
    kind: str
    title: str
    content: str
    payload: str
    deleted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
