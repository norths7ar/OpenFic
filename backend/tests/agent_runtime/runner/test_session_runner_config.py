import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent_runtime.runner.run_registry import AgentRunRegistry
from app.agent_runtime.tools.impls.orchestration.common import ensure_child_processing


@pytest.mark.asyncio
async def test_register_can_preserve_session_cancellation() -> None:
    registry = AgentRunRegistry()
    blocker = asyncio.Event()
    task = asyncio.create_task(blocker.wait())
    try:
        await registry.mark_cancelled("session-cancelled")
        await registry.register("session-cancelled", task, clear_cancelled=False)

        assert await registry.is_cancelled("session-cancelled") is True
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_child_resume_does_not_clear_session_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = AgentRunRegistry()
    monkeypatch.setattr(
        "app.agent_runtime.tools.impls.orchestration.common.get_agent_run_registry",
        lambda: registry,
    )
    await registry.mark_cancelled("session-cancelled")

    class Runner:
        called = False

        async def resume(self, child_run_id: str, payload: dict) -> None:
            self.called = True

    runner = Runner()
    started = await ensure_child_processing(
        parent_session_id="session-cancelled",
        child_run_id="child-1",
        runner=runner,
        resume_payload={"approved": True},
        clear_cancelled=False,
    )

    assert started is False
    assert runner.called is False
    assert await registry.is_cancelled("session-cancelled") is True
    assert await registry.is_child_running("session-cancelled", "child-1") is False


@pytest.mark.asyncio
async def test_child_completion_continuation_preserves_session_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.agent_runtime.runner.subagent_runner import SubagentRunner

    ensure = AsyncMock()
    monkeypatch.setattr(
        "app.agent_runtime.tools.impls.orchestration.common.ensure_child_processing",
        ensure,
    )
    runner = SubagentRunner(
        session_factory=None,
        model_config={},
        project_id="p1",
    )
    monkeypatch.setattr(
        runner,
        "_load_child_run",
        AsyncMock(
            return_value=SimpleNamespace(
                is_active=True,
                status="queued",
            )
        ),
    )
    monkeypatch.setattr(runner, "_count_pending_requests", AsyncMock(return_value=1))

    await runner.on_child_processing_finished(
        parent_session_id="session-cancelled",
        child_run_id="child-1",
    )

    assert ensure.await_args is not None
    assert ensure.await_args.kwargs["clear_cancelled"] is False
