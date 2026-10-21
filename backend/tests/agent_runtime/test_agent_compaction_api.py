import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent_runtime.runner.run_registry import AgentRunRegistry
from app.api.routers import agent_runtime
from app.api.routers.agent_runtime import _SESSION_RUNNERS


@pytest.fixture(autouse=True)
def reset_agent_runtime_runners():
    _SESSION_RUNNERS.clear()
    try:
        yield
    finally:
        _SESSION_RUNNERS.clear()


def _runner(
    *,
    compact_result: dict | None = None,
    compact_error: Exception | None = None,
    pending: tuple[str, str] | None = None,
):
    runner = SimpleNamespace(
        session_id="sess_compaction_api",
        task_id="task_compaction_api",
        project_id="proj_compaction_api",
        peek_next_pending_user_message=MagicMock(return_value=pending),
        consume_next_pending_user_message_for_continuation=AsyncMock(return_value=pending),
        run=MagicMock(return_value=object()),
    )
    if compact_error is not None:
        runner.compact = AsyncMock(side_effect=compact_error)
    else:
        runner.compact = AsyncMock(
            return_value=compact_result
            or {
                "compaction_id": "cmp_api_1",
                "start_seq": 2,
                "end_seq": 7,
                "source_input_tokens": 1234,
                "summary_tokens": 98,
            }
        )
    return runner


@pytest.mark.asyncio
async def test_manual_compaction_can_be_cancelled_while_model_call_is_waiting() -> None:
    runner = _runner()
    compact_started = asyncio.Event()
    release_compact = asyncio.Event()

    async def blocked_compact():
        compact_started.set()
        await release_compact.wait()
        return {
            "compaction_id": "cmp_api_1",
            "start_seq": 2,
            "end_seq": 7,
        }

    runner.compact = AsyncMock(side_effect=blocked_compact)
    registry = AgentRunRegistry()
    session = SimpleNamespace(bind=MagicMock())

    with (
        patch(
            "app.api.routers.agent_runtime._ensure_agent_session_resumable",
            AsyncMock(),
        ),
        patch(
            "app.api.routers.agent_runtime._set_task_running_state",
            AsyncMock(),
        ),
    ):
        compaction_task = asyncio.create_task(
            agent_runtime._run_agent_session_compaction(
                session_id=runner.session_id,
                session=session,
                runner=runner,
                registry=registry,
            )
        )
        await asyncio.wait_for(compact_started.wait(), timeout=1)

        lifecycle_lock = registry.session_lock(runner.session_id)
        await asyncio.wait_for(lifecycle_lock.acquire(), timeout=1)
        try:
            parent_task = await registry.mark_cancelled(runner.session_id)
            assert parent_task is compaction_task
            assert await registry.cancel_task(runner.session_id, parent_task)
        finally:
            lifecycle_lock.release()

        with pytest.raises(asyncio.CancelledError):
            await compaction_task

    runner.compact.assert_awaited_once_with()
    assert not release_compact.is_set()
