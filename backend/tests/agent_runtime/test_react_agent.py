import asyncio
import json
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import BaseModel

from app.agent_runtime.graph.react_agent import (
    ReactState,
    create_react_agent,
)
from app.agent_runtime.tools.base import AgentTool, HookResult
from app.agent_runtime.tools.errors import ToolExecutionError
from app.agent_runtime.types import ReactAgentConfig, TerminationCondition


class ApprovalInput(BaseModel):
    value: str


async def _approval_hook(ctx) -> HookResult:
    return HookResult(
        proceed=False,
        interrupt_payload={
            "type": "tool_approval",
            "tool_name": ctx.tool_name,
            "args": ctx.args,
        },
    )


class ApprovalTool(AgentTool):
    name: str = "approval_tool"
    description: str = "requires approval"
    access_level: str = "write"
    args_schema: type[BaseModel] = ApprovalInput

    async def build_interrupt_preview(self, args: dict[str, object]) -> dict | None:
        if self.config is None:
            return None
        return {
            "type": "preview",
            "success": True,
            "metadata": {"value": args["value"]},
        }

    async def _execute(self, value: str) -> str:
        return json.dumps({"success": True, "value": value})


@pytest.mark.asyncio
async def test_react_agent_does_not_execute_tool_after_approval_is_rejected() -> None:
    executed: list[str] = []
    tool_results: list[dict] = []

    class RejectableTool(ApprovalTool):
        async def _execute(self, value: str) -> str:
            executed.append(value)
            return await super()._execute(value)

    graph = create_react_agent(
        ReactAgentConfig(
            name="test",
            tools=[RejectableTool(_pre_hooks=[_approval_hook])],
            termination=TerminationCondition(mode="no_tool_call"),
            max_iterations=1,
        ),
        checkpointer=InMemorySaver(),
    )

    async def invoke_model(*_args, **_kwargs):
        return AIMessage(
            content="",
            tool_calls=[{"id": "call_reject", "name": "approval_tool", "args": {"value": "x"}}],
        )

    config = {"configurable": {"thread_id": "reject-approval"}}
    config["configurable"]["tool_result_sink"] = tool_results.append
    with patch(
        "app.agent_runtime.graph.react_agent._invoke_model",
        side_effect=invoke_model,
    ):
        await graph.ainvoke(
            {
                "messages": [HumanMessage(content="run")],
                "iteration_count": 0,
                "is_done": False,
                "final_output": None,
            },
            config=config,
        )
        state = await graph.aget_state(config)
        pending = [
            interrupt for task in state.tasks for interrupt in getattr(task, "interrupts", ())
        ]
        await graph.ainvoke(
            Command(
                resume={
                    pending[0].id: {
                        "action_type": "tool_approval",
                        "approval_id": pending[0].id,
                        "approved": False,
                    }
                }
            ),
            config=config,
        )

    assert executed == []
    assert len(tool_results) == 1
    assert tool_results[0]["tool_call_id"] == "call_reject"
    assert tool_results[0]["output"] == {
        "type": "control",
        "success": False,
        "status": "approval_denied",
        "message": "工具调用已被用户拒绝",
        "approval_id": pending[0].id,
        "tool_name": "approval_tool",
        "tool_call_id": "call_reject",
    }


def _batch_state() -> ReactState:
    return {
        "messages": [HumanMessage(content="run")],
        "iteration_count": 0,
        "is_done": False,
        "final_output": None,
    }


def _batch_response(count: int, name: str = "counting_tool") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"id": f"call_{index}", "name": name, "args": {"value": str(index)}}
            for index in range(count)
        ],
    )


@pytest.mark.asyncio
async def test_react_agent_preserves_failures_and_successes_across_batches() -> None:
    executed = []
    tool_results = []

    async def counting_tool(value: str) -> str:
        executed.append(value)
        if value in {"19", "20", "40"}:
            raise ToolExecutionError(f"failed:{value}", code="not_found")
        return json.dumps({"success": True, "value": value})

    response = _batch_response(45)
    response.tool_calls[21]["name"] = "missing_tool"
    graph = create_react_agent(
        ReactAgentConfig(
            name="test",
            tools=[StructuredTool.from_function(coroutine=counting_tool, description="count")],
            termination=TerminationCondition(mode="no_tool_call"),
            max_iterations=1,
        )
    )
    with patch("app.agent_runtime.graph.react_agent._invoke_model", return_value=response) as model:
        result = await graph.ainvoke(
            _batch_state(), config={"configurable": {"tool_result_sink": tool_results.append}}
        )
    model.assert_awaited_once()
    assert sorted(executed, key=int) == [str(i) for i in range(45) if i != 21]
    messages = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [message.tool_call_id for message in messages] == [f"call_{i}" for i in range(45)]
    for i, message in enumerate(messages):
        payload = json.loads(message.content)
        if i in {19, 20, 40}:
            assert payload["code"] == "not_found"
            assert payload["success"] is False
        elif i == 21:
            assert payload["code"] == "tool_not_found"
        else:
            assert payload == {"success": True, "value": str(i)}
    assert sorted(item["tool_call_id"] for item in tool_results) == [
        "call_19",
        "call_20",
        "call_40",
    ]


@pytest.mark.asyncio
async def test_react_agent_prepares_all_batches_before_resuming_late_rejection() -> None:
    prepared = set()
    executed = []
    tool_results = []

    async def prepare(ctx):
        prepared.add(ctx.args["value"])
        if ctx.args["value"] in {"20", "44"}:
            return await _approval_hook(ctx)
        return HookResult()

    class CountingApprovalTool(ApprovalTool):
        async def _execute(self, value: str) -> str:
            assert prepared == {str(i) for i in range(45)}
            executed.append(value)
            return await super()._execute(value)

    graph = create_react_agent(
        ReactAgentConfig(
            name="test",
            tools=[CountingApprovalTool(_pre_hooks=[prepare])],
            termination=TerminationCondition(mode="no_tool_call"),
            max_iterations=1,
        ),
        checkpointer=InMemorySaver(),
    )
    config = {
        "configurable": {
            "thread_id": "cross-batch-approval",
            "tool_result_sink": tool_results.append,
        }
    }
    with patch(
        "app.agent_runtime.graph.react_agent._invoke_model",
        return_value=_batch_response(45, "approval_tool"),
    ) as model:
        await graph.ainvoke(_batch_state(), config=config)
        approval_ids = []
        for index, approved in [(20, True), (44, False)]:
            state = await graph.aget_state(config)
            pending = [interrupt for task in state.tasks for interrupt in task.interrupts]
            assert len(pending) == 1
            interrupt = pending[0]
            approval_ids.append(interrupt.id)
            assert interrupt.value["tool_call_id"] == f"call_{index}"
            assert interrupt.value["tool_index"] == index
            assert interrupt.value["args"] == {"value": str(index)}
            assert interrupt.value["tool_result_preview"]["metadata"] == {"value": str(index)}
            assert executed == []
            assert tool_results == []
            result = await graph.ainvoke(
                Command(
                    resume={
                        interrupt.id: {
                            "action_type": "tool_approval",
                            "approval_id": interrupt.id,
                            "approved": approved,
                        }
                    }
                ),
                config=config,
            )
    model.assert_awaited_once()
    assert len(set(approval_ids)) == 2
    assert sorted(executed, key=int) == [str(i) for i in range(44)]
    assert (await graph.aget_state(config)).next == ()
    messages = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [message.tool_call_id for message in messages] == [f"call_{i}" for i in range(45)]
    assert [json.loads(message.content)["value"] for message in messages[:-1]] == [
        str(i) for i in range(44)
    ]
    denied = json.loads(messages[-1].content)
    assert denied["status"] == "approval_denied"
    assert denied["approval_id"] == approval_ids[-1]
    assert len(tool_results) == 1
    assert tool_results[0]["tool_call_id"] == "call_44"
    assert tool_results[0]["output"]["approval_id"] == approval_ids[-1]


@pytest.mark.asyncio
async def test_react_agent_cancellation_stops_active_batch_and_never_starts_later_batch() -> None:
    started = []
    cancelled = []
    batch_started = asyncio.Event()
    blocked = asyncio.Event()

    async def counting_tool(value: str) -> str:
        started.append(value)
        if len(started) == 20:
            batch_started.set()
        try:
            await blocked.wait()
        except asyncio.CancelledError:
            cancelled.append(value)
            raise
        return '{"success": true}'

    graph = create_react_agent(
        ReactAgentConfig(
            name="test",
            tools=[StructuredTool.from_function(coroutine=counting_tool, description="count")],
            termination=TerminationCondition(mode="no_tool_call"),
            max_iterations=1,
        )
    )
    with patch(
        "app.agent_runtime.graph.react_agent._invoke_model", return_value=_batch_response(45)
    ) as model:
        task = asyncio.create_task(graph.ainvoke(_batch_state()))
        try:
            await asyncio.wait_for(batch_started.wait(), timeout=5)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=5)
    model.assert_awaited_once()
    assert sorted(started, key=int) == [str(i) for i in range(20)]
    assert sorted(cancelled, key=int) == sorted(started, key=int)
