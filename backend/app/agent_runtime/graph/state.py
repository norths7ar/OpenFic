from typing import Any, Literal, NotRequired, TypedDict


class AgentRuntimeState(TypedDict):
    session_id: str
    task_id: str
    project_id: str
    context_mode: Literal["global", "local"]
    model_config: dict
    active_agent: str | None
    agent_key: str
    is_completed: bool
    error: str | None
    retry_count: int
    user_request: str
    user_attachments: list[dict[str, Any]]
    current_revision_id: str | None
    current_message_id: NotRequired[str | None]
    referenced_skill_ids: NotRequired[list[str]]
