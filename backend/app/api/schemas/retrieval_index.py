"""Schemas for project retrieval index APIs."""

from typing import Annotated

from pydantic import Field, WithJsonSchema

from app.api.schemas.base import APIModel

IndexStatus = Annotated[
    str,
    WithJsonSchema(
        {
            "type": "string",
            "enum": [
                "disabled",
                "not_configured",
                "no_chapters",
                "no_index",
                "indexing",
                "needs_rebuild",
                "stale",
                "fresh",
                "failed",
            ],
        }
    ),
]
IndexMode = Annotated[str, WithJsonSchema({"type": "string", "enum": ["off", "all", "selected"]})]


class IndexProjectStatusResponse(APIModel):
    """单个项目的索引状态汇总（不含内部 ID）。"""

    project_id: str
    enabled: bool
    status: IndexStatus
    title: str = ""
    total_chapters: int = 0
    indexed_count: int = 0
    pending_count: int = 0
    in_progress_count: int = 0
    failed_count: int = 0
    empty_content_count: int = 0
    last_error: str | None = None
    progress: float = 0.0


class IndexOverallStatusResponse(APIModel):
    """索引总体状态（跨启用项目聚合）。"""

    mode: IndexMode
    embedding_model_configured: bool
    total_projects: int = 0
    total_chapters: int = 0
    indexed_count: int = 0
    pending_count: int = 0
    in_progress_count: int = 0
    failed_count: int = 0
    projects: list[IndexProjectStatusResponse] = Field(default_factory=list)


class IndexStartResponse(APIModel):
    """手动开始索引的响应。"""

    project_id: str
    enqueued_count: int
    skipped_count: int = 0


class IndexStopResponse(APIModel):
    """手动停止索引的响应。"""

    project_id: str
    stopped_count: int
