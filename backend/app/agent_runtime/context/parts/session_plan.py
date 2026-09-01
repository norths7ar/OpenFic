from __future__ import annotations

from collections.abc import Mapping, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.context.errors import ContextBuildError
from app.agent_runtime.context.types import ContextMessage
from app.agent_runtime.plan import service as plan_service

_PLAN_AWARE_AGENTS = {"build", "plan", "discuss"}


def _has_active_todos(todos: Sequence[Mapping[str, str]]) -> bool:
    return any(todo.get("status") in {"pending", "in_progress"} for todo in todos)


def _has_matching_write_plan_result(
    history: Sequence[ContextMessage],
    formatted_plan: str,
) -> bool:
    return any(
        message.role == "tool"
        and (
            message.name == "write_plan"
            or (message.metadata or {}).get("tool_name") == "write_plan"
        )
        and message.content.strip() == formatted_plan
        for message in history
    )


async def build_session_plan(
    state: Mapping[str, object],
    agent_name: str,
    history: Sequence[ContextMessage],
    db_session: AsyncSession,
) -> ContextMessage | None:
    if agent_name not in _PLAN_AWARE_AGENTS:
        return None

    session_id = state.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return None

    try:
        todos = await plan_service.get_plan_todos(db_session, session_id)
    except Exception as exc:
        raise ContextBuildError(
            "session_plan",
            "failed to load current session plan",
            cause=exc,
        ) from exc

    if not todos or not _has_active_todos(todos):
        return None

    formatted_plan = plan_service.format_plan_todos(todos)
    has_recent_snapshot = _has_matching_write_plan_result(history, formatted_plan)
    if agent_name != "discuss" and has_recent_snapshot:
        return None

    if agent_name == "discuss":
        guidance = (
            "当前会话存在计划，仅供理解讨论背景。除非用户明确要求，否则不要执行、推进或修改该计划。"
        )
        content = guidance if has_recent_snapshot else f"{guidance}\n\n{formatted_plan}"
    else:
        content = (
            "以下是当前会话的权威计划状态。执行任务时参考，并在状态发生变化时更新计划。"
            f"\n\n{formatted_plan}"
        )

    return ContextMessage(
        role="system",
        content=f"<current-session-plan>\n{content}\n</current-session-plan>",
        metadata={"part": "session_plan", "mode": agent_name},
    )
