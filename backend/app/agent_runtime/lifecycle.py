"""Agent run lifecycle operations with explicit status transaction ownership.

Status changes commit in an independent session before their events are emitted.
Cancellation walks descendants before parents; callers own the main transaction.
"""

import time
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.persistence.child_runs import (
    TERMINAL_CHILD_RUN_STATUSES,
    cancel_child_run,
    list_child_runs_for_parent,
)
from app.agent_runtime.persistence.model import AgentChildRun
from app.agent_runtime.runner.subagent_runner import SubagentRunner
from app.socket import emit
from app.socket.handlers import background_project_room
from app.storage.services import task_service


async def _list_descendant_child_runs(
    session: AsyncSession,
    *,
    parent_session_id: str,
) -> list[AgentChildRun]:
    descendants: list[AgentChildRun] = []
    for row in await list_child_runs_for_parent(session, parent_session_id):
        descendants.extend(
            await _list_descendant_child_runs(
                session,
                parent_session_id=row.child_thread_id,
            )
        )
        descendants.append(row)
    return descendants


async def _cancel_subagent_session_tree(
    session: AsyncSession,
    *,
    root_session_id: str,
    registry,
    status_publisher: SubagentRunner | None = None,
) -> None:
    descendants = await _list_descendant_child_runs(
        session,
        parent_session_id=root_session_id,
    )

    session_ids_to_cancel: list[str] = []
    seen_session_ids: set[str] = set()
    for session_id in [*(row.child_thread_id for row in descendants), root_session_id]:
        if session_id in seen_session_ids:
            continue
        seen_session_ids.add(session_id)
        session_ids_to_cancel.append(session_id)

    for session_id in session_ids_to_cancel:
        await registry.cancel(session_id)

    for row in descendants:
        if not row.is_active:
            continue
        if row.status in TERMINAL_CHILD_RUN_STATUSES:
            continue
        await cancel_child_run(
            session,
            row.id,
            error="parent session cancelled",
        )
        if status_publisher is not None:
            await status_publisher.publish_parent_subagent_status(row.id)


async def _set_task_running_state(
    *,
    db_session_factory: Callable[[], AsyncSession],
    task_id: str,
    session_id: str,
    project_id: str,
    is_running: bool,
) -> None:
    status_session = db_session_factory()
    try:
        task = await task_service.update_task(
            status_session,
            task_id=task_id,
            is_running=is_running,
        )
        await status_session.commit()
    finally:
        await status_session.close()

    if project_id:
        await emit(
            "background:event",
            {
                "type": "task_run_status_updated",
                "job_type": "agent_runtime",
                "subject_type": "project",
                "subject_id": project_id,
                "project_id": project_id,
                "task_id": task_id,
                "agent_session_id": session_id,
                "is_running": is_running,
                "payload": {"is_running": is_running},
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": task.updated_at.isoformat(),
                "project_revision": time.time_ns(),
            },
            room=background_project_room(project_id),
        )

    await emit(
        "agent:settings_lock_changed",
        {
            "session_id": session_id,
            "is_running": is_running,
        },
    )


def _make_status_session_factory(session: AsyncSession) -> Callable[[], AsyncSession]:
    if session.bind is None:
        raise RuntimeError("数据库会话未绑定连接")
    factory = async_sessionmaker(
        session.bind,
        expire_on_commit=False,
    )
    return factory
