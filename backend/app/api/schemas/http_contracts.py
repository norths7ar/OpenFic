"""Small fixed HTTP envelopes shared by the corresponding routes."""

from typing import Any, Literal

from app.api.schemas.base import APIModel
from app.core.agent_visibility import AgentVisibilityState
from app.project_bundle.importer import PreviewItem


class CountResponse(APIModel):
    count: int


class UpdatedCountResponse(APIModel):
    updated_count: int


class DeletedCountResponse(APIModel):
    deleted_count: int


class DeletedTasksResponse(DeletedCountResponse):
    skipped_running_count: int


class AgentVisibilityCatalogResponse(APIModel):
    default: str
    states: list[AgentVisibilityState]


class AgentTodo(APIModel):
    content: str
    status: Literal["pending", "in_progress", "completed"]
    priority: Literal["low", "medium", "high"]


class AgentTodosResponse(APIModel):
    todos: list[AgentTodo]


class PendingAgentMessage(APIModel):
    message_id: str
    content: str
    created_at: str
    delivery_mode: str


class PendingAgentMessagesResponse(APIModel):
    items: list[PendingAgentMessage]


class AgentSubmissionResponse(APIModel):
    success: bool
    session_id: str
    message: str


class SourceBundleItem(APIModel):
    source: str
    rule_id: str
    target: str
    anchor: str
    title: str
    section: str | None
    category_path: list[str]
    agent_visibility: str
    order: int


class BundleApplyResponse(APIModel):
    mode: str
    items: list[PreviewItem]
    summary: dict[str, int]


class BundlePreviewResponse(BundleApplyResponse):
    source_project: dict[str, Any]


class SourceBundleResponse(BundleApplyResponse):
    source_items: list[SourceBundleItem]
