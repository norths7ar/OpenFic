import json
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from app.agent_runtime.tools.base import AgentTool, HookContext, HookResult


class DummyInput(BaseModel):
    value: str


class PreviewTool(AgentTool):
    name: str = "preview"
    description: str = "A tool with approval preview"
    access_level: str = "write"
    args_schema: type[BaseModel] = DummyInput

    async def build_interrupt_preview(self, args: dict[str, object]) -> dict | None:
        return {
            "type": "preview",
            "success": True,
            "data": {"value": args.get("value")},
        }

    async def _execute(self, value: str) -> str:
        return f"executed:{value}"


def _make_state() -> dict:
    return {
        "session_id": "sess-1",
        "project_id": "proj-1",
        "model_config": {},
        "active_agent": None,
        "is_completed": False,
        "error": None,
        "retry_count": 0,
        "message_checkpoints": [],
        "user_request": "",
    }


async def test_agent_tool_builds_tool_preview_for_tool_approval_interrupt():
    async def blocking_hook(ctx: HookContext) -> HookResult:
        return HookResult(
            proceed=False,
            interrupt_payload={
                "type": "tool_approval",
                "tool_name": ctx.tool_name,
                "args": ctx.args,
            },
        )

    tool = PreviewTool(_state=_make_state(), _pre_hooks=[blocking_hook])
    captured: list[dict] = []

    def fake_interrupt(payload: dict) -> None:
        captured.append(payload)
        raise RuntimeError("interrupted")

    with patch("langgraph.types.interrupt", side_effect=fake_interrupt):
        with pytest.raises(RuntimeError, match="interrupted"):
            await tool.ainvoke(
                {"value": "hello"},
                config={"metadata": {"tool_call_id": "call-1"}},
            )

    assert captured[0]["tool_call_id"] == "call-1"
    assert captured[0]["tool_result_preview"] == {
        "type": "preview",
        "success": True,
        "data": {"value": "hello"},
    }


async def test_agent_tool_does_not_execute_after_rejected_tool_approval():
    executed: list[str] = []

    class GuardedTool(PreviewTool):
        async def _execute(self, value: str) -> str:
            executed.append(value)
            return f"executed:{value}"

    async def blocking_hook(ctx: HookContext) -> HookResult:
        return HookResult(
            proceed=False,
            interrupt_payload={
                "type": "tool_approval",
                "tool_name": ctx.tool_name,
                "args": ctx.args,
            },
        )

    tool = GuardedTool(_state=_make_state(), _pre_hooks=[blocking_hook])

    with patch(
        "langgraph.types.interrupt",
        return_value={
            "action_type": "tool_approval",
            "approval_id": "approval-1",
            "approved": False,
        },
    ):
        result = await tool.ainvoke({"value": "hello"})

    payload = json.loads(result)
    assert payload == {
        "type": "control",
        "success": False,
        "status": "approval_denied",
        "message": "工具调用已被用户拒绝",
        "approval_id": "approval-1",
        "tool_name": "preview",
    }
    assert executed == []
