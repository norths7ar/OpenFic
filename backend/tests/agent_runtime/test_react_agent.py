import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.messages.tool import invalid_tool_call
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import BaseModel

from app.agent_runtime.graph.react_agent import (
    ReactState,
    _invoke_model,
    _invoke_tool,
    _tool_result_payload,
    create_react_agent,
)
from app.agent_runtime.tools.base import AgentTool, HookResult
from app.agent_runtime.tools.errors import ToolExecutionError
from app.agent_runtime.types import ReactAgentConfig, TerminationCondition
from app.settings import settings


async def _proceed_hook(_ctx) -> HookResult:
    return HookResult()


def _submit_result(result: str) -> str:
    return f"submitted: {result}"


def _add_numbers(a: int, b: int) -> int:
    return a + b


async def _async_submit_result(result: str) -> str:
    return _submit_result(result)


async def _async_add_numbers(a: int, b: int) -> int:
    return _add_numbers(a, b)


def _write_plan_tool(executed_calls: list[dict[str, object]]) -> StructuredTool:
    async def _async_write_plan(todos: list[dict[str, str]]) -> str:
        executed_calls.append({"todos": todos})
        return "written"

    return StructuredTool.from_function(
        coroutine=_async_write_plan,
        name="write_plan",
        description="write plan",
    )


def _submit_tool() -> StructuredTool:
    return StructuredTool.from_function(
        coroutine=_async_submit_result,
        name="submit_result",
        description="submit",
    )


def _add_tool() -> StructuredTool:
    return StructuredTool.from_function(
        coroutine=_async_add_numbers,
        name="add_numbers",
        description="add",
    )


def _sync_add_tool() -> StructuredTool:
    return StructuredTool.from_function(
        _add_numbers,
        name="add_numbers",
        description="add",
    )


def _metadata_tool() -> StructuredTool:
    async def _async_edit() -> str:
        return '{"success":true,"metadata":{"chapter_diff":{"chapter_id":"chap-1"}}}'

    return StructuredTool.from_function(
        coroutine=_async_edit,
        name="edit_chapter",
        description="edit",
    )


def test_react_state_is_valid_typed_dict():
    state: ReactState = {
        "messages": [],
        "iteration_count": 0,
        "is_done": False,
        "final_output": None,
    }
    assert state["iteration_count"] == 0


@pytest.mark.asyncio
async def test_invoke_model_normalizes_recoverable_invalid_tool_calls_to_ai_message() -> None:
    class StreamingModel:
        async def astream(self, _messages):
            yield AIMessageChunk(
                content="",
                invalid_tool_calls=[
                    invalid_tool_call(
                        id="call_edit_note",
                        name="edit_note",
                        args='{"note_ref":{"path":"/outline"},"content":"updated"}',
                        error="invalid json",
                    )
                ],
            )

    response = await _invoke_model(StreamingModel(), [HumanMessage(content="Update the note")])

    assert type(response) is AIMessage
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["id"] == "call_edit_note"
    assert response.tool_calls[0]["name"] == "edit_note"
    assert response.tool_calls[0]["args"] == {
        "note_ref": {"path": "/outline"},
        "content": "updated",
    }
    assert response.invalid_tool_calls == []


@pytest.mark.asyncio
async def test_invoke_model_extracts_anthropic_text_content_blocks() -> None:
    class StreamingModel:
        async def astream(self, _messages):
            yield AIMessageChunk(
                content=[
                    {"type": "thinking", "thinking": "分析中"},
                    {"type": "text", "text": "可见回复"},
                ]
            )

    response = await _invoke_model(StreamingModel(), [HumanMessage(content="Hello")])

    assert response.content == "可见回复"


@pytest.mark.asyncio
async def test_invoke_model_sanitizes_nested_message_metadata() -> None:
    nested_message = AIMessage(content="nested")

    class StreamingModel:
        async def astream(self, _messages):
            yield AIMessageChunk(
                content="完成",
                response_metadata={"raw_message": nested_message},
            )

    response = await _invoke_model(StreamingModel(), [HumanMessage(content="Hello")])

    assert response.response_metadata["raw_message"]["content"] == "nested"
    assert not isinstance(response.response_metadata["raw_message"], AIMessage)


def test_create_react_agent_returns_compiled_graph(dummy_tool):
    config = ReactAgentConfig(
        name="test",
        tools=[dummy_tool],
        termination=TerminationCondition(mode="no_tool_call"),
    )
    graph = create_react_agent(config, checkpointer=InMemorySaver())
    assert graph is not None
    assert hasattr(graph, "ainvoke")


def test_create_react_agent_with_tool_success_termination(submit_tool):
    config = ReactAgentConfig(
        name="test",
        tools=[submit_tool],
        termination=TerminationCondition(mode="tool_success", tool_name="submit_result"),
    )
    graph = create_react_agent(config, checkpointer=InMemorySaver())
    assert graph is not None


def test_react_agent_terminates_on_no_tool_call(dummy_tool):
    config = ReactAgentConfig(
        name="test",
        tools=[dummy_tool],
        termination=TerminationCondition(mode="no_tool_call"),
    )
    graph = create_react_agent(config)

    async def _mock_invoke(*args, **kwargs):
        return AIMessage(content="Done, no tools needed.")

    async def _run():
        with patch(
            "app.agent_runtime.graph.react_agent._invoke_model",
            side_effect=_mock_invoke,
        ):
            result = await graph.ainvoke(
                {
                    "messages": [HumanMessage(content="Hello")],
                    "iteration_count": 0,
                    "is_done": False,
                    "final_output": None,
                }
            )
            assert result["is_done"] is True

    asyncio.run(_run())


@pytest.mark.asyncio
async def test_react_agent_normalizes_structured_tool_exception() -> None:
    async def failing_tool() -> str:
        raise RuntimeError("structured tool failure")

    tool = StructuredTool.from_function(
        coroutine=failing_tool,
        name="failing_tool",
        description="fails",
    )
    model = Mock()
    model.bind_tools.return_value = model
    responses = iter(
        [
            AIMessage(
                content="",
                tool_calls=[{"id": "call-1", "name": "failing_tool", "args": {}}],
            ),
            AIMessage(content="recovered"),
        ]
    )

    async def invoke_model(*_args, **_kwargs):
        return next(responses)

    config = ReactAgentConfig(
        name="writer",
        tools=[tool],
        termination=TerminationCondition(mode="no_tool_call"),
        max_iterations=2,
    )
    tool_results: list[dict] = []

    with patch(
        "app.agent_runtime.graph.react_agent._invoke_model",
        side_effect=invoke_model,
    ):
        result = await create_react_agent(config, model=model).ainvoke(
            {
                "messages": [HumanMessage(content="go")],
                "iteration_count": 0,
                "is_done": False,
                "final_output": None,
            },
            config={"configurable": {"tool_result_sink": tool_results.append}},
        )

    tool_messages = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert json.loads(tool_messages[0].content) == {
        "type": "fail",
        "success": False,
        "code": "execution_failed",
        "message": "structured tool failure",
    }
    assert result["messages"][-1].content == "recovered"
    assert tool_results == [
        {
            "session_id": None,
            "tool_call_id": "call-1",
            "tool_name": "failing_tool",
            "input": {},
            "output": {
                "type": "fail",
                "success": False,
                "code": "execution_failed",
                "message": "structured tool failure",
                "tool_call_id": "call-1",
                "tool_name": "failing_tool",
            },
        }
    ]


@pytest.mark.asyncio
async def test_react_agent_preserves_structured_tool_error_code() -> None:
    async def failing_tool() -> str:
        raise ToolExecutionError("章节不存在", code="not_found")

    tool = StructuredTool.from_function(
        coroutine=failing_tool,
        name="failing_tool",
        description="fails",
    )
    model = Mock()
    model.bind_tools.return_value = model
    responses = iter(
        [
            AIMessage(
                content="",
                tool_calls=[{"id": "call-1", "name": "failing_tool", "args": {}}],
            ),
            AIMessage(content="recovered"),
        ]
    )

    async def invoke_model(*_args, **_kwargs):
        return next(responses)

    with patch(
        "app.agent_runtime.graph.react_agent._invoke_model",
        side_effect=invoke_model,
    ):
        result = await create_react_agent(
            ReactAgentConfig(
                name="writer",
                tools=[tool],
                termination=TerminationCondition(mode="no_tool_call"),
                max_iterations=2,
            ),
            model=model,
        ).ainvoke(
            {
                "messages": [HumanMessage(content="go")],
                "iteration_count": 0,
                "is_done": False,
                "final_output": None,
            }
        )

    tool_message = next(
        message for message in result["messages"] if isinstance(message, ToolMessage)
    )
    assert json.loads(tool_message.content)["code"] == "not_found"


@pytest.mark.asyncio
async def test_react_agent_terminates_on_tool_success():
    config = ReactAgentConfig(
        name="test",
        tools=[_submit_tool()],
        termination=TerminationCondition(mode="tool_success", tool_name="submit_result"),
    )
    graph = create_react_agent(config)

    async def _mock_invoke(*args, **kwargs):
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "submit_result",
                    "args": {"result": "analysis complete"},
                }
            ],
        )

    with (
        patch(
            "app.agent_runtime.graph.react_agent._invoke_model",
            side_effect=_mock_invoke,
        ),
        patch(
            "app.agent_runtime.graph.react_agent.build_context",
            new=AsyncMock(return_value=[HumanMessage(content="Use a tool")]),
        ),
    ):
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Analyze this")],
                "iteration_count": 0,
                "is_done": False,
                "final_output": None,
            }
        )
        assert result["is_done"] is True
        assert result["final_output"] == {"result": "analysis complete"}


@pytest.mark.asyncio
async def test_react_agent_emits_retry_event_for_retryable_llm_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "llm_retry_base_interval", 0.0)
    monkeypatch.setattr(settings, "llm_retry_max_interval", 0.0)
    config = ReactAgentConfig(
        name="writer",
        tools=[],
        termination=TerminationCondition(mode="no_tool_call"),
    )
    graph = create_react_agent(config)
    retry_events: list[dict] = []

    async def _retry_event_sink(payload: dict) -> None:
        retry_events.append(payload)

    class _UpstreamError(Exception):
        status_code = 503

    responses = [
        _UpstreamError("temporary upstream failure"),
        AIMessage(content="final answer"),
    ]

    async def _mock_invoke(*args, **kwargs):
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    with patch("app.agent_runtime.graph.react_agent._invoke_model", side_effect=_mock_invoke):
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Hello")],
                "iteration_count": 0,
                "is_done": False,
                "final_output": None,
            },
            config={
                "configurable": {
                    "runtime_state": {"session_id": "sess_001"},
                    "retry_event_sink": _retry_event_sink,
                },
            },
        )

    assert result["is_done"] is True
    assert retry_events == [
        {
            "session_id": "sess_001",
            "node": "writer",
            "attempt": 2,
            "max_attempts": 5,
            "error_type": "_UpstreamError",
            "error_message": "temporary upstream failure",
            "error_category": "http",
            "retry_in_ms": 0,
        }
    ]


@pytest.mark.asyncio
async def test_react_agent_retry_leaves_clean_checkpoint_and_history(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "llm_retry_base_interval", 0.0)
    monkeypatch.setattr(settings, "llm_retry_max_interval", 0.0)

    class _UpstreamError(Exception):
        status_code = 503

    class _FlakyModel:
        def __init__(self, responses):
            self._responses = list(responses)

        def bind_tools(self, tools):
            return self

        def astream(self, messages):
            return self._astream()

        async def _astream(self):
            item = self._responses.pop(0)
            if isinstance(item, Exception):
                raise item
            yield item

    retry_events: list[dict] = []

    async def _retry_event_sink(payload: dict) -> None:
        retry_events.append(payload)

    config = ReactAgentConfig(
        name="writer",
        tools=[],
        termination=TerminationCondition(mode="no_tool_call"),
    )
    thread_id = "retry-thread-1"
    graph = create_react_agent(
        config,
        model=_FlakyModel(
            [
                _UpstreamError("upstream boom"),
                AIMessage(content="final answer"),
            ]
        ),
        checkpointer=InMemorySaver(),
    )

    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="Hello")],
            "iteration_count": 0,
            "is_done": False,
            "final_output": None,
        },
        config={
            "configurable": {
                "runtime_state": {"session_id": "sess_retry"},
                "thread_id": thread_id,
                "retry_event_sink": _retry_event_sink,
            },
        },
    )

    assert result["is_done"] is True
    assert len(result["messages"]) == 2
    assert result["messages"][1].content == "final answer"
    assert len(retry_events) == 1
    assert retry_events[0]["attempt"] == 2

    checkpoint = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    checkpoint_messages = checkpoint.values.get("messages", [])
    assert [message.content for message in checkpoint_messages] == [
        "Hello",
        "final answer",
    ]
    assert checkpoint.values.get("iteration_count") == 1


@pytest.mark.asyncio
async def test_react_agent_executes_termination_tool_on_final_iteration():
    config = ReactAgentConfig(
        name="test",
        tools=[_submit_tool()],
        termination=TerminationCondition(mode="tool_success", tool_name="submit_result"),
        max_iterations=1,
    )
    graph = create_react_agent(config)

    async def _mock_invoke(*args, **kwargs):
        return AIMessage(
            content="",
            tool_calls=[{"id": "call_1", "name": "submit_result", "args": {"result": "done"}}],
        )

    with patch("app.agent_runtime.graph.react_agent._invoke_model", side_effect=_mock_invoke):
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Analyze this")],
                "iteration_count": 0,
                "is_done": False,
                "final_output": None,
            }
        )

    assert result["is_done"] is True
    assert result["iteration_count"] == 1
    assert result["final_output"] == {"result": "done"}


@pytest.mark.asyncio
async def test_react_agent_executes_tool_call_and_stops():
    config = ReactAgentConfig(
        name="test",
        tools=[_add_tool()],
        termination=TerminationCondition(mode="no_tool_call"),
        max_iterations=2,
    )
    graph = create_react_agent(config)

    call_count = 0

    async def mock_invoke_with_tools(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "id": f"call_{call_count}",
                    "name": "add_numbers",
                    "args": {"a": 1, "b": 2},
                }
            ],
        )

    with patch(
        "app.agent_runtime.graph.react_agent._invoke_model",
        side_effect=mock_invoke_with_tools,
    ):
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Keep calling tools")],
                "iteration_count": 0,
                "is_done": False,
                "final_output": None,
            }
        )
        assert result["is_done"] is True
        assert result["iteration_count"] == 2


@pytest.mark.asyncio
async def test_react_agent_keeps_tool_result_metadata_in_graph_state():
    config = ReactAgentConfig(
        name="test",
        tools=[_metadata_tool()],
        termination=TerminationCondition(mode="no_tool_call"),
        max_iterations=2,
    )
    graph = create_react_agent(config)
    observed_messages: list[list] = []
    responses = [
        AIMessage(
            content="",
            tool_calls=[{"id": "call_1", "name": "edit_chapter", "args": {}}],
        ),
        AIMessage(content="done"),
    ]

    async def mock_invoke(_model, messages, **_kwargs):
        observed_messages.append(messages)
        return responses.pop(0)

    with patch("app.agent_runtime.graph.react_agent._invoke_model", side_effect=mock_invoke):
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="编辑章节")],
                "iteration_count": 0,
                "is_done": False,
                "final_output": None,
            }
        )

    state_tool_message = result["messages"][-2]
    assert isinstance(state_tool_message, ToolMessage)
    assert json.loads(state_tool_message.content) == {
        "success": True,
        "metadata": {"chapter_diff": {"chapter_id": "chap-1"}},
    }
    model_tool_message = observed_messages[1][-1]
    assert isinstance(model_tool_message, ToolMessage)
    assert model_tool_message.content == '{"success": true}'


@pytest.mark.asyncio
async def test_react_agent_streams_tool_events_for_frontend():
    config = ReactAgentConfig(
        name="test",
        tools=[_submit_tool()],
        termination=TerminationCondition(mode="tool_success", tool_name="submit_result"),
    )
    graph = create_react_agent(config)

    async def _mock_invoke(*args, **kwargs):
        return AIMessage(
            content="",
            tool_calls=[{"id": "call_1", "name": "submit_result", "args": {"result": "done"}}],
        )

    tool_events = []
    with (
        patch(
            "app.agent_runtime.graph.react_agent._invoke_model",
            side_effect=_mock_invoke,
        ),
        patch(
            "app.agent_runtime.graph.react_agent.build_context",
            new=AsyncMock(return_value=[HumanMessage(content="Use a tool")]),
        ),
    ):
        async for event in graph.astream_events(
            {
                "messages": [HumanMessage(content="Analyze this")],
                "iteration_count": 0,
                "is_done": False,
                "final_output": None,
            },
            version="v2",
        ):
            if event["event"] in {"on_tool_start", "on_tool_end"}:
                tool_events.append(event)

    assert [event["event"] for event in tool_events] == ["on_tool_start", "on_tool_end"]
    assert [event["name"] for event in tool_events] == [
        "submit_result",
        "submit_result",
    ]
    assert tool_events[0]["metadata"]["tool_call_id"] == "call_1"
    assert tool_events[1]["metadata"]["tool_call_id"] == "call_1"
    assert tool_events[0]["data"]["input"] == {"result": "done"}
    assert tool_events[1]["data"]["output"] == "submitted: done"


@pytest.mark.asyncio
async def test_react_agent_continues_after_auxiliary_tool_until_termination_tool():
    config = ReactAgentConfig(
        name="test",
        tools=[_add_tool(), _submit_tool()],
        termination=TerminationCondition(mode="tool_success", tool_name="submit_result"),
        max_iterations=3,
    )
    graph = create_react_agent(config)

    responses = [
        AIMessage(
            content="",
            tool_calls=[{"id": "call_1", "name": "add_numbers", "args": {"a": 1, "b": 2}}],
        ),
        AIMessage(
            content="",
            tool_calls=[{"id": "call_2", "name": "submit_result", "args": {"result": "done"}}],
        ),
    ]

    async def _mock_invoke(*args, **kwargs):
        return responses.pop(0)

    with patch("app.agent_runtime.graph.react_agent._invoke_model", side_effect=_mock_invoke):
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Use a helper first")],
                "iteration_count": 0,
                "is_done": False,
                "final_output": None,
            }
        )

    assert result["is_done"] is True
    assert result["iteration_count"] == 2
    assert result["final_output"] == {"result": "done"}


@pytest.mark.asyncio
async def test_react_agent_ignores_no_tool_response_until_termination_tool():
    config = ReactAgentConfig(
        name="test",
        tools=[_add_tool(), _submit_tool()],
        termination=TerminationCondition(mode="tool_success", tool_name="submit_result"),
        max_iterations=4,
    )
    graph = create_react_agent(config)

    responses = [
        AIMessage(
            content="",
            tool_calls=[{"id": "call_1", "name": "add_numbers", "args": {"a": 1, "b": 2}}],
        ),
        AIMessage(content="I reviewed the intermediate result."),
        AIMessage(
            content="",
            tool_calls=[{"id": "call_2", "name": "submit_result", "args": {"result": "done"}}],
        ),
    ]

    async def _mock_invoke(*args, **kwargs):
        return responses.pop(0)

    with patch("app.agent_runtime.graph.react_agent._invoke_model", side_effect=_mock_invoke):
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Use a helper first")],
                "iteration_count": 0,
                "is_done": False,
                "final_output": None,
            }
        )

    assert result["is_done"] is True
    assert result["iteration_count"] == 3
    assert result["final_output"] == {"result": "done"}


@pytest.mark.asyncio
async def test_react_agent_raises_when_tool_success_lacks_termination_tool():
    config = ReactAgentConfig(
        name="test",
        tools=[_add_tool(), _submit_tool()],
        termination=TerminationCondition(mode="tool_success", tool_name="submit_result"),
        max_iterations=2,
    )
    graph = create_react_agent(config)

    responses = [
        AIMessage(content="I reviewed it."),
        AIMessage(content="Still done in plain text."),
    ]

    async def _mock_invoke(*args, **kwargs):
        return responses.pop(0)

    with (
        patch(
            "app.agent_runtime.graph.react_agent._invoke_model",
            side_effect=_mock_invoke,
        ),
        pytest.raises(RuntimeError, match="submit_result"),
    ):
        await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Use the submit tool")],
                "iteration_count": 0,
                "is_done": False,
                "final_output": None,
            }
        )


@pytest.mark.asyncio
async def test_react_agent_recovers_malformed_write_plan_todos_invalid_tool_call():
    executed_calls: list[dict[str, object]] = []
    config = ReactAgentConfig(
        name="composer",
        tools=[_write_plan_tool(executed_calls)],
        termination=TerminationCondition(mode="tool_success", tool_name="write_plan"),
        max_iterations=1,
    )
    graph = create_react_agent(config)
    malformed_args = (
        '{"todos":[{"content":"line1\nline2","status":"pending","priority":"high"},'
        '{"content":"done","status":"completed","priority":"low"}]}'
    )

    async def _mock_invoke(*args, **kwargs):
        return AIMessage(
            content="",
            invalid_tool_calls=[
                invalid_tool_call(
                    id="call_1",
                    name="write_plan",
                    args=malformed_args,
                    error="invalid json in todos array",
                )
            ],
        )

    with patch("app.agent_runtime.graph.react_agent._invoke_model", side_effect=_mock_invoke):
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Create a plan")],
                "iteration_count": 0,
                "is_done": False,
                "final_output": None,
            }
        )

    assert result["is_done"] is True
    assert result["final_output"] == {
        "todos": [
            {"content": "line1\nline2", "status": "pending", "priority": "high"},
            {"content": "done", "status": "completed", "priority": "low"},
        ],
    }
    assert executed_calls == [result["final_output"]]


@pytest.mark.asyncio
async def test_react_agent_emits_tool_error_for_unrecoverable_invalid_tool_call_with_existing_id():
    executed_calls: list[dict[str, object]] = []
    config = ReactAgentConfig(
        name="composer",
        tools=[_write_plan_tool(executed_calls)],
        termination=TerminationCondition(mode="no_tool_call"),
        max_iterations=1,
    )
    graph = create_react_agent(config)

    async def _mock_invoke(*args, **kwargs):
        return AIMessage(
            content="",
            invalid_tool_calls=[
                invalid_tool_call(
                    id="call_1",
                    name="write_plan",
                    args="<<<<",
                    error="invalid json",
                )
            ],
        )

    with patch("app.agent_runtime.graph.react_agent._invoke_model", side_effect=_mock_invoke):
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Create a plan")],
                "iteration_count": 0,
                "is_done": False,
                "final_output": None,
            }
        )

    assert executed_calls == []
    assert isinstance(result["messages"][-1], ToolMessage)
    assert result["messages"][-1].tool_call_id == "call_1"
    assert json.loads(result["messages"][-1].content) == {
        "type": "fail",
        "success": False,
        "code": "malformed_tool_call",
        "message": "工具参数 JSON 无法解析，未执行工具调用",
    }


def test_tool_result_payload_treats_canonical_failure_as_failure() -> None:
    payload, success = _tool_result_payload(
        '{"type":"fail","success":false,"code":"not_found","message":"未找到章节"}'
    )

    assert payload["code"] == "not_found"
    assert success is False


def test_tool_result_payload_treats_failed_type_as_failure_without_success() -> None:
    payload, success = _tool_result_payload(
        '{"type":"fail","code":"not_found","message":"未找到章节"}'
    )

    assert payload["code"] == "not_found"
    assert success is False


@pytest.mark.asyncio
async def test_react_agent_returns_canonical_failure_for_unknown_tool() -> None:
    config = ReactAgentConfig(
        name="composer",
        tools=[_add_tool()],
        termination=TerminationCondition(mode="no_tool_call"),
        max_iterations=2,
    )
    graph = create_react_agent(config)
    calls = 0

    async def _mock_invoke(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return AIMessage(
                content="",
                tool_calls=[{"id": "call_unknown", "name": "missing_tool", "args": {}}],
            )
        return AIMessage(content="done")

    with patch("app.agent_runtime.graph.react_agent._invoke_model", side_effect=_mock_invoke):
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="run")],
                "iteration_count": 0,
                "is_done": False,
                "final_output": None,
            }
        )

    tool_message = next(
        message for message in result["messages"] if isinstance(message, ToolMessage)
    )
    assert json.loads(tool_message.content) == {
        "type": "fail",
        "success": False,
        "code": "tool_not_found",
        "message": "未找到工具：missing_tool",
    }


@pytest.mark.asyncio
async def test_react_agent_synthesizes_tool_call_id_for_unrecoverable_invalid_tool_call():
    executed_calls: list[dict[str, object]] = []
    config = ReactAgentConfig(
        name="composer",
        tools=[_write_plan_tool(executed_calls)],
        termination=TerminationCondition(mode="no_tool_call"),
        max_iterations=1,
    )
    graph = create_react_agent(config)

    async def _mock_invoke(*args, **kwargs):
        return AIMessage(
            content="",
            invalid_tool_calls=[
                {
                    "name": "write_plan",
                    "args": "<<<<",
                    "error": "invalid json",
                    "type": "invalid_tool_call",
                }
            ],
        )

    with patch("app.agent_runtime.graph.react_agent._invoke_model", side_effect=_mock_invoke):
        result = await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Create a plan")],
                "iteration_count": 0,
                "is_done": False,
                "final_output": None,
            }
        )

    assistant_message = result["messages"][-2]
    tool_message = result["messages"][-1]
    assert executed_calls == []
    assert isinstance(assistant_message, AIMessage)
    assert isinstance(tool_message, ToolMessage)
    assert len(assistant_message.tool_calls) == 1
    synthesized_id = assistant_message.tool_calls[0]["id"]
    assert isinstance(synthesized_id, str) and synthesized_id
    assert tool_message.tool_call_id == synthesized_id


def test_invoke_tool_executes_sync_structured_tool_without_executor():
    async def _run():
        result = await _invoke_tool(_sync_add_tool(), {"a": 2, "b": 3})
        assert result == 5

    asyncio.run(_run())


class CaptureConfigInput(BaseModel):
    value: str


class CaptureConfigTool(AgentTool):
    name: str = "capture_config"
    description: str = "capture config"
    access_level: str = "readonly"
    args_schema: type[BaseModel] = CaptureConfigInput

    async def _execute(self, value: str) -> str:
        return value


@pytest.mark.asyncio
async def test_react_agent_passes_runtime_config_and_tool_call_id_to_agent_tools():
    captured = []

    async def post_hook(ctx):
        captured.append(ctx)
        return HookResult()

    config = ReactAgentConfig(
        name="test",
        tools=[CaptureConfigTool(_post_hooks=[post_hook])],
        termination=TerminationCondition(mode="tool_success", tool_name="capture_config"),
    )
    graph = create_react_agent(config)

    async def _mock_invoke(*args, **kwargs):
        return AIMessage(
            content="",
            tool_calls=[{"id": "call_1", "name": "capture_config", "args": {"value": "done"}}],
        )

    with (
        patch(
            "app.agent_runtime.graph.react_agent._invoke_model",
            side_effect=_mock_invoke,
        ),
        patch(
            "app.agent_runtime.graph.react_agent.build_context",
            new=AsyncMock(return_value=[HumanMessage(content="Use a tool")]),
        ),
        patch(
            "app.agent_runtime.graph.react_agent.normalize_tool_failure_result",
            side_effect=AssertionError("AgentTool result was normalized twice"),
        ),
    ):
        await graph.ainvoke(
            {
                "messages": [HumanMessage(content="Use a tool")],
                "iteration_count": 0,
                "is_done": False,
                "final_output": None,
            },
            config={
                "configurable": {
                    "db_session": "session",
                    "runtime_state": {"active_agent": "writer"},
                }
            },
        )

    assert captured[0].tool_call_id == "call_1"
    assert captured[0].config["configurable"]["db_session"] == "session"


class ApprovalInput(BaseModel):
    value: str


@pytest.mark.asyncio
async def test_react_agent_attaches_tool_metadata_to_ask_user_interrupt() -> None:
    from app.agent_runtime.tools.impls.interaction.ask_user import AskUserTool

    graph = create_react_agent(
        ReactAgentConfig(
            name="test",
            tools=[AskUserTool(_pre_hooks=[_proceed_hook])],
            termination=TerminationCondition(mode="no_tool_call"),
            max_iterations=1,
        ),
        checkpointer=InMemorySaver(),
    )

    async def invoke_model(*_args, **_kwargs):
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_ask",
                    "name": "ask_user",
                    "args": {
                        "questions": [
                            {
                                "title": "剧情走向？",
                                "description": "请选择下一段的展开方向。",
                                "options": [],
                            }
                        ]
                    },
                }
            ],
        )

    config = {"configurable": {"thread_id": "ask-user-interrupt"}}
    with patch(
        "app.agent_runtime.graph.react_agent._invoke_model",
        side_effect=invoke_model,
    ):
        await graph.ainvoke(
            {
                "messages": [HumanMessage(content="继续")],
                "iteration_count": 0,
                "is_done": False,
                "final_output": None,
            },
            config=config,
        )

    state = await graph.aget_state(config)
    pending = [
        pending_interrupt
        for task in state.tasks
        for pending_interrupt in getattr(task, "interrupts", ())
    ]
    assert len(pending) == 1
    assert pending[0].value["tool_call_id"] == "call_ask"
    assert pending[0].value["tool_name"] == "ask_user"
    assert pending[0].value["args"] == {
        "questions": [
            {
                "title": "剧情走向？",
                "description": "请选择下一段的展开方向。",
                "options": [],
            }
        ]
    }


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
@pytest.mark.parametrize("count", [20, 21, 45])
async def test_react_agent_executes_all_tool_calls_in_bounded_batches(count: int) -> None:
    executed: list[str] = []
    active = 0
    peak = 0
    gates = [asyncio.Event() for _ in range((count + 19) // 20)]
    started = [0] * len(gates)

    async def counting_tool(value: str) -> str:
        nonlocal active, peak
        index = int(value)
        batch = index // 20
        active += 1
        peak = max(peak, active)
        started[batch] += 1
        if started[batch] == min(20, count - batch * 20):
            gates[batch].set()
        try:
            await asyncio.wait_for(gates[batch].wait(), timeout=5)
            # Finish out of order so aggregation cannot rely on completion order.
            await asyncio.sleep((20 - index % 20) * 0.001)
            executed.append(value)
            return json.dumps({"success": True, "value": value})
        finally:
            active -= 1

    graph = create_react_agent(
        ReactAgentConfig(
            name="test",
            tools=[StructuredTool.from_function(coroutine=counting_tool, description="count")],
            termination=TerminationCondition(mode="no_tool_call"),
            max_iterations=1,
        ),
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": f"batch-{count}"}}
    events = []
    with patch(
        "app.agent_runtime.graph.react_agent._invoke_model",
        return_value=_batch_response(count),
    ) as invoke_model:
        async for event in graph.astream_events(_batch_state(), config=config, version="v2"):
            if event["event"] in {"on_tool_start", "on_tool_end"}:
                events.append(event)
    result = (await graph.aget_state(config)).values
    invoke_model.assert_awaited_once()
    assert result["iteration_count"] == 1
    assert peak == 20
    assert active == 0
    assert sorted(executed, key=int) == [str(index) for index in range(count)]
    messages = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [message.tool_call_id for message in messages] == [f"call_{i}" for i in range(count)]
    assert [json.loads(message.content)["value"] for message in messages] == [
        str(i) for i in range(count)
    ]
    for kind in ("on_tool_start", "on_tool_end"):
        ids = [event["metadata"]["tool_call_id"] for event in events if event["event"] == kind]
        assert sorted(ids) == sorted(f"call_{i}" for i in range(count))


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
async def test_react_agent_limits_subagent_dispatches_per_model_turn_not_batch() -> None:
    dispatched = []
    ordinary = []

    async def dispatch_subagent(value: str) -> str:
        dispatched.append(value)
        return '{"success": true}'

    async def counting_tool(value: str) -> str:
        ordinary.append(value)
        return '{"success": true}'

    response = _batch_response(25)
    # Seven dispatches in the first batch leave only three permits for the second.
    dispatch_indices = [0, 1, 2, 3, 4, 5, 19, 20, 21, 22, 23, 24]
    for index in dispatch_indices:
        response.tool_calls[index]["name"] = "dispatch_subagent"
    second = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "next_turn",
                "name": "dispatch_subagent",
                "args": {"value": "next"},
            }
        ],
    )
    graph = create_react_agent(
        ReactAgentConfig(
            name="test",
            tools=[
                StructuredTool.from_function(coroutine=tool, description="count")
                for tool in [dispatch_subagent, counting_tool]
            ],
            termination=TerminationCondition(mode="no_tool_call"),
            max_iterations=2,
        )
    )
    with patch(
        "app.agent_runtime.graph.react_agent._invoke_model", side_effect=[response, second]
    ) as model:
        result = await graph.ainvoke(_batch_state())
    assert model.await_count == 2
    assert result["iteration_count"] == 2
    assert dispatched == [str(i) for i in dispatch_indices[:10]] + ["next"]
    assert ordinary == [str(i) for i in range(25) if i not in dispatch_indices]
    messages = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [message.tool_call_id for message in messages] == [f"call_{i}" for i in range(25)] + [
        "next_turn"
    ]
    assert [
        message.tool_call_id
        for message in messages
        if json.loads(message.content).get("code") == "limit_exceeded"
    ] == ["call_23", "call_24"]


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


@pytest.mark.asyncio
async def test_react_agent_previews_all_parallel_tool_calls_and_resumes_each_approval() -> None:
    response = AIMessage(
        content="",
        tool_calls=[
            {
                "id": f"call_{index}",
                "name": "approval_tool",
                "args": {"value": str(index)},
            }
            for index in range(1, 6)
        ],
    )
    config = ReactAgentConfig(
        name="test",
        tools=[ApprovalTool(_pre_hooks=[_approval_hook])],
        termination=TerminationCondition(mode="no_tool_call"),
        max_iterations=1,
    )
    graph = create_react_agent(config, checkpointer=InMemorySaver())

    async def _mock_invoke(*args, **kwargs):
        return response

    with patch("app.agent_runtime.graph.react_agent._invoke_model", side_effect=_mock_invoke):
        config = {"configurable": {"db_session": object(), "thread_id": "parallel-approval"}}
        await graph.ainvoke(
            {
                "messages": [HumanMessage(content="run both")],
                "iteration_count": 0,
                "is_done": False,
                "final_output": None,
            },
            config=config,
        )
        state = await graph.aget_state(config)

    interrupts = [
        interrupt for task in state.tasks for interrupt in getattr(task, "interrupts", ())
    ]
    assert {interrupt.value["tool_call_id"] for interrupt in interrupts} == {
        f"call_{index}" for index in range(1, 6)
    }
    assert len({interrupt.id for interrupt in interrupts}) == 5
    pending_interrupts = list(interrupts)

    for _index in range(1, 6):
        interrupt = pending_interrupts.pop(0)
        await graph.ainvoke(
            Command(
                resume={
                    interrupt.id: {
                        "action_type": "tool_approval",
                        "approval_id": interrupt.id,
                        "approved": True,
                    }
                }
            ),
            config=config,
        )
        resumed_state = await graph.aget_state(config)
        interrupts = [
            interrupt
            for task in resumed_state.tasks
            for interrupt in getattr(task, "interrupts", ())
        ]
        if _index < 5:
            assert len(resumed_state.next) == 5 - _index
        else:
            assert resumed_state.next == ()

    tool_messages = [
        message for message in resumed_state.values["messages"] if isinstance(message, ToolMessage)
    ]
    assert [json.loads(message.content)["value"] for message in tool_messages] == [
        str(index) for index in range(1, 6)
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "persisted_overflow", [False, True], ids=["before-dispatch", "after-dispatch"]
)
async def test_react_agent_resumes_legacy_execution_without_running_overflow(
    persisted_overflow: bool,
) -> None:
    executed = []
    hook_calls = []
    bypassed_hooks = []
    tool_results = []
    # The old graph prepared only these calls before checkpointing execution.
    prepared = {str(i) for i in range(20)}

    async def prepare(ctx):
        value = ctx.args["value"]
        hook_calls.append(value)
        prepared.add(value)
        return HookResult()

    class LegacyProbeTool(ApprovalTool):
        async def _execute(self, value: str) -> str:
            if value not in prepared:
                bypassed_hooks.append(value)
            executed.append(value)
            return await super()._execute(value)

    response = _batch_response(21, "approval_tool")
    overflow_payload = {
        "type": "fail",
        "success": False,
        "code": "limit_exceeded",
        "message": "Agent 单轮最多调用 20 个工具，超出上限的工具调用未执行",
    }

    def outcome(index: int, payload: dict, success: bool) -> dict:
        call = response.tool_calls[index]
        return {
            "index": index,
            "tool_call_id": call["id"],
            "tool_name": call["name"],
            "tool_args": call["args"],
            "message": ToolMessage(
                content=json.dumps(payload),
                tool_call_id=call["id"],
                name=call["name"],
            ),
            "payload": payload,
            "success": success,
            "latency_ms": 0,
        }

    graph = create_react_agent(
        ReactAgentConfig(
            name="test",
            tools=[LegacyProbeTool(_pre_hooks=[prepare])],
            termination=TerminationCondition(mode="no_tool_call"),
            max_iterations=2,
        ),
        checkpointer=InMemorySaver(),
    )
    config = {
        "configurable": {
            "thread_id": f"legacy-execution-{persisted_overflow}",
            "session_id": "legacy-session",
            "tool_result_sink": tool_results.append,
        }
    }
    legacy_state = {
        **_batch_state(),
        "messages": [HumanMessage(content="run"), response],
        "iteration_count": 1,
        "tool_phase": "execute",
        "tool_prepared_outcomes": [
            outcome(i, {"__openfic_prepared": True}, True) for i in range(20)
        ],
        "tool_outcomes": [outcome(20, overflow_payload, False)] if persisted_overflow else [],
    }
    # Reconstruct the two old checkpoint boundaries without adding the new offset.
    await graph.aupdate_state(
        config,
        legacy_state,
        as_node="dispatch_tools" if persisted_overflow else "tools_join",
    )
    saved = await graph.aget_state(config)
    assert "tool_batch_offset" not in saved.values
    assert saved.values["tool_phase"] == "execute"
    assert len(saved.values["tool_prepared_outcomes"]) == 20
    assert saved.next == (
        tuple(f"tool_exec_{i}" for i in range(20)) if persisted_overflow else ("dispatch_tools",)
    )

    next_response = AIMessage(
        content="",
        tool_calls=[
            {"id": f"next_{i}", "name": "approval_tool", "args": {"value": f"next_{i}"}}
            for i in range(21)
        ],
    )

    async def next_model_turn(_model, messages, **_kwargs):
        # No replay of the old model turn, no preparation or execution of its overflow.
        assert sorted(executed, key=int) == [str(i) for i in range(20)]
        assert hook_calls == []
        assert bypassed_hooks == []
        legacy_messages = [message for message in messages if isinstance(message, ToolMessage)]
        assert [message.tool_call_id for message in legacy_messages] == [
            f"call_{i}" for i in range(21)
        ]
        return next_response

    with patch(
        "app.agent_runtime.graph.react_agent._invoke_model",
        side_effect=next_model_turn,
    ) as model:
        result = await graph.ainvoke(None, config=config)
    model.assert_awaited_once()
    assert result["iteration_count"] == 2
    assert result["is_done"] is True
    assert bypassed_hooks == []
    assert executed[:20] == [str(i) for i in range(20)]
    assert executed[20:] == [f"next_{i}" for i in range(21)]
    assert hook_calls == [f"next_{i}" for i in range(21)]
    messages = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [message.tool_call_id for message in messages] == [f"call_{i}" for i in range(21)] + [
        f"next_{i}" for i in range(21)
    ]
    for message in messages[:20] + messages[21:]:
        assert json.loads(message.content)["success"] is True
    overflow = json.loads(messages[20].content)
    assert overflow["code"] == "limit_exceeded"
    assert overflow["success"] is False
    if persisted_overflow:
        assert overflow == overflow_payload
        assert tool_results == []
    else:
        assert tool_results == [
            {
                "session_id": "legacy-session",
                "tool_call_id": "call_20",
                "tool_name": "approval_tool",
                "input": {"value": "20"},
                "output": {**overflow, "tool_call_id": "call_20", "tool_name": "approval_tool"},
            }
        ]
    assert (await graph.aget_state(config)).next == ()
