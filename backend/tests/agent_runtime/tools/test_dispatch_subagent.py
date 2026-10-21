import json
from types import SimpleNamespace

import pytest

from app.agent_runtime.tools.errors import ToolExecutionError
from app.agent_runtime.tools.impls.orchestration.dispatch_subagent import (
    DispatchSubagentTool,
)


@pytest.mark.asyncio
async def test_dispatch_subagent_returns_dispatch_id_when_child_request_is_cancelled(
    monkeypatch: pytest.MonkeyPatch,
):
    import app.agent_runtime.tools.impls.orchestration.dispatch_subagent as dispatch_module

    row = SimpleNamespace(
        id="child-run-1",
        child_thread_id="parent:child:dispatch-cancelled",
        dispatch_id="dispatch-cancelled",
        metadata_json={"agent_number": 3},
        pending_approval_json=None,
    )

    async def noop(*_args, **_kwargs) -> None:
        return None

    async def open_session(*_args, **_kwargs) -> object:
        return object()

    async def load_waiting_child_run(*_args, **_kwargs):
        return None

    async def create_child_run(*_args, **_kwargs):
        return row

    async def persist_child_user_message(*_args, **_kwargs):
        return SimpleNamespace(id="message-1", seq=1)

    async def load_initial_request_id(*_args, **_kwargs) -> str:
        return "request-1"

    async def wait_for_assistant_content(*_args, **_kwargs) -> str:
        raise ToolExecutionError("subagent request was cancelled")

    class Runner:
        async def publish_parent_subagent_status(self, _child_run_id: str) -> None:
            return None

    monkeypatch.setattr(DispatchSubagentTool, "_validate_dispatch", noop)
    monkeypatch.setattr(
        DispatchSubagentTool,
        "_load_waiting_child_run",
        load_waiting_child_run,
    )
    monkeypatch.setattr(DispatchSubagentTool, "_create_child_run", create_child_run)
    monkeypatch.setattr(
        DispatchSubagentTool,
        "_load_initial_request_id",
        load_initial_request_id,
    )
    monkeypatch.setattr(
        DispatchSubagentTool,
        "_wait_for_assistant_content",
        wait_for_assistant_content,
    )
    monkeypatch.setattr(dispatch_module, "latest_checkpoint_id_for_thread", noop)
    monkeypatch.setattr(dispatch_module, "persist_child_user_message", persist_child_user_message)
    monkeypatch.setattr(dispatch_module, "open_session", open_session)
    monkeypatch.setattr(dispatch_module, "close_session", noop)
    monkeypatch.setattr(dispatch_module, "update_child_run_request_boundaries", noop)
    monkeypatch.setattr(dispatch_module, "make_subagent_runner", lambda **_kwargs: Runner())

    tool = DispatchSubagentTool(
        _state={
            "session_id": "parent",
            "task_id": "task-1",
            "project_id": "project-1",
        }
    )

    result = json.loads(
        await tool._arun(
            agent_type="writer",
            description="write scene",
            prompt="write scene",
        )
    )

    assert result == {
        "dispatch_id": "dispatch-cancelled",
        "agent_number": 3,
        "type": "fail",
        "success": False,
        "code": "execution_failed",
        "message": "subagent request was cancelled",
    }
