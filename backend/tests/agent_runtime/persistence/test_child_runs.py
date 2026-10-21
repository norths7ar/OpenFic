import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.agent_runtime.persistence.child_runs import (
    cancel_interrupted_child_runs,
    create_child_run,
)
from app.agent_runtime.persistence.model import (
    AgentChildRun,
    AgentChildRunRequest,
)


@pytest.mark.asyncio
async def test_cancel_interrupted_child_runs_finalizes_all_active_runs(
    db_session: AsyncSession,
    sample_task,
):
    queued = await create_child_run(
        db_session,
        parent_session_id="parent-session",
        parent_task_id=sample_task.id,
        parent_thread_id="parent-thread",
        child_thread_id="queued-child",
        agent_key="writer",
        dispatch_id="dispatch-queued",
        tool_call_id="tool-call-queued",
        request={},
        status="queued",
    )
    running = await create_child_run(
        db_session,
        parent_session_id="parent-session",
        parent_task_id=sample_task.id,
        parent_thread_id="parent-thread",
        child_thread_id="running-child",
        agent_key="reviewer",
        dispatch_id="dispatch-running",
        tool_call_id="tool-call-running",
        request={},
        status="running",
    )
    waiting = await create_child_run(
        db_session,
        parent_session_id="parent-session",
        parent_task_id=sample_task.id,
        parent_thread_id="parent-thread",
        child_thread_id="waiting-child",
        agent_key="composer",
        dispatch_id="dispatch-waiting",
        tool_call_id="tool-call-waiting",
        request={},
        status="waiting_user",
    )

    cancelled = await cancel_interrupted_child_runs(db_session)

    assert cancelled == 3
    for child_run_id in (queued.id, running.id, waiting.id):
        row = await db_session.get(AgentChildRun, child_run_id)
        assert row is not None
        assert row.status == "cancelled"
        assert row.completed_at is not None
        assert row.last_completed_at is not None
        assert row.error == "server restarted"

        result = await db_session.execute(
            select(AgentChildRunRequest).where(
                col(AgentChildRunRequest.child_run_id) == child_run_id
            )
        )
        requests = list(result.scalars().all())
        assert requests
        assert all(request.status == "cancelled" for request in requests)
        assert all(request.error == "server restarted" for request in requests)
        assert all(request.completed_at is not None for request in requests)
