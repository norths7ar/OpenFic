"""MessagePersister 测试 — 流式保存与中断收尾。"""

import json

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.persistence import repo
from app.agent_runtime.persistence.persister import MessagePersister


@pytest.mark.asyncio
async def test_persister_normal_chat_model_stream(
    db_session: AsyncSession, db_session_factory, sample_task
):
    sid = "session_a"
    p = MessagePersister(
        session_id=sid,
        task_id=sample_task.id,
        project_id=sample_task.project_id,
        db_session_factory=db_session_factory,
    )

    await p.handle(
        {
            "event": "on_chain_start",
            "name": "writer",
            "tags": ["agent_node"],
            "data": {},
        }
    )
    await p.handle({"event": "on_chat_model_start", "data": {}})
    await p.handle(
        {
            "event": "on_chat_model_stream",
            "data": {"chunk": AIMessageChunk(content="hello ")},
        }
    )
    await p.handle(
        {
            "event": "on_chat_model_stream",
            "data": {"chunk": AIMessageChunk(content="world")},
        }
    )
    await p.handle(
        {
            "event": "on_chat_model_end",
            "data": {"output": AIMessageChunk(content="hello world")},
        }
    )

    items = await repo.list_by_session(db_session, sid)
    assert len(items) == 1
    msg = items[0]
    assert msg.role == "assistant"
    assert msg.status == "complete"
    assert msg.content == "hello world"
    assert msg.agent_id == "writer"


@pytest.mark.asyncio
async def test_persister_persists_non_streaming_chat_model_end_output(
    db_session: AsyncSession, db_session_factory, sample_task
):
    sid = "session_non_streaming"
    p = MessagePersister(
        session_id=sid,
        task_id=sample_task.id,
        project_id=sample_task.project_id,
        db_session_factory=db_session_factory,
    )

    await p.handle(
        {
            "event": "on_chain_start",
            "name": "composer",
            "tags": ["agent_node"],
            "data": {},
        }
    )
    await p.handle(
        {
            "event": "on_chat_model_start",
            "run_id": "non-stream-run",
            "data": {},
        }
    )
    await p.handle(
        {
            "event": "on_chat_model_end",
            "run_id": "non-stream-run",
            "data": {"output": AIMessage(content="final non-stream answer")},
        }
    )

    items = await repo.list_by_session(db_session, sid)
    assert len(items) == 1
    assert items[0].role == "assistant"
    assert items[0].status == "complete"
    assert items[0].content == "final non-stream answer"
    assert items[0].agent_id == "composer"


@pytest.mark.asyncio
async def test_persister_ignores_subagent_child_events(
    db_session: AsyncSession, db_session_factory, sample_task
):
    sid = "session_parent"
    p = MessagePersister(
        session_id=sid,
        task_id=sample_task.id,
        project_id=sample_task.project_id,
        db_session_factory=db_session_factory,
    )

    await p.handle({"event": "on_chat_model_start", "tags": ["subagent_child"], "data": {}})
    await p.handle(
        {
            "event": "on_chat_model_stream",
            "tags": ["subagent_child"],
            "data": {"chunk": AIMessageChunk(content="hidden child output")},
        }
    )
    await p.handle(
        {
            "event": "on_chat_model_end",
            "tags": ["subagent_child"],
            "data": {"output": AIMessageChunk(content="hidden child output")},
        }
    )
    await p.handle(
        {
            "event": "on_tool_end",
            "name": "read_chapter",
            "run_id": "child-tool-run",
            "tags": ["subagent_child"],
            "data": {"output": "hidden child tool result"},
        }
    )

    items = await repo.list_by_session(db_session, sid)
    assert items == []


@pytest.mark.asyncio
async def test_persister_tool_start_end_writes_tool_complete(
    db_session: AsyncSession, db_session_factory, sample_task
):
    sid = "session_a"
    p = MessagePersister(
        session_id=sid,
        task_id=sample_task.id,
        project_id=sample_task.project_id,
        db_session_factory=db_session_factory,
    )
    await p.handle(
        {
            "event": "on_tool_start",
            "name": "read_chapter",
            "run_id": "run-1",
            "data": {"input": {"order": 1}},
            "metadata": {"tool_call_id": "c1"},
        }
    )
    await p.handle(
        {
            "event": "on_tool_end",
            "name": "read_chapter",
            "run_id": "run-1",
            "data": {"output": "chapter body"},
        }
    )

    items = await repo.list_by_session(db_session, sid)
    assert len(items) == 1
    msg = items[0]
    assert msg.role == "tool"
    assert msg.status == "complete"
    assert msg.tool_call_id == "c1"
    assert msg.tool_name == "read_chapter"
    assert msg.content == "chapter body"


@pytest.mark.asyncio
async def test_persister_assistant_with_tool_calls(
    db_session: AsyncSession, db_session_factory, sample_task
):
    sid = "session_a"
    p = MessagePersister(
        session_id=sid,
        task_id=sample_task.id,
        project_id=sample_task.project_id,
        db_session_factory=db_session_factory,
    )
    await p.handle({"event": "on_chat_model_start", "data": {}})
    chunk = AIMessageChunk(
        content="",
        tool_call_chunks=[{"index": 0, "id": "c1", "name": "read_chapter", "args": ""}],
    )
    await p.handle({"event": "on_chat_model_stream", "data": {"chunk": chunk}})
    chunk2 = AIMessageChunk(
        content="",
        tool_call_chunks=[{"index": 0, "id": None, "name": None, "args": '{"order":1}'}],
    )
    await p.handle({"event": "on_chat_model_stream", "data": {"chunk": chunk2}})
    await p.handle({"event": "on_chat_model_end", "data": {}})

    items = await repo.list_by_session(db_session, sid)
    assert len(items) == 1
    assert items[0].role == "assistant"
    assert items[0].status == "complete"
    assert items[0].tool_calls == [{"id": "c1", "name": "read_chapter", "args": {"order": 1}}]


@pytest.mark.asyncio
async def test_finalize_writes_partial_assistant_with_resolvable_tool_call(
    db_session: AsyncSession, db_session_factory, sample_task
):
    sid = "session_a"
    p = MessagePersister(
        session_id=sid,
        task_id=sample_task.id,
        project_id=sample_task.project_id,
        db_session_factory=db_session_factory,
    )
    await p.handle({"event": "on_chat_model_start", "data": {}})
    await p.handle(
        {
            "event": "on_chat_model_stream",
            "data": {"chunk": AIMessageChunk(content="half-")},
        }
    )
    chunk = AIMessageChunk(
        content="",
        tool_call_chunks=[{"index": 0, "id": "c1", "name": "read_chapter", "args": '{"order":1}'}],
    )
    await p.handle({"event": "on_chat_model_stream", "data": {"chunk": chunk}})

    await p.finalize(reason="cancelled")

    items = await repo.list_by_session(db_session, sid)
    roles = [(m.role, m.status) for m in items]
    assert ("assistant", "partial") in roles
    assert ("tool", "aborted") in roles
    assistant = next(m for m in items if m.role == "assistant")
    assert assistant.content == "half-"
    assert assistant.tool_calls == [{"id": "c1", "name": "read_chapter", "args": {"order": 1}}]
    tool = next(m for m in items if m.role == "tool")
    assert tool.tool_call_id == "c1"
    assert tool.tool_name == "read_chapter"
    assert json.loads(tool.content) == {
        "type": "fail",
        "success": False,
        "code": "execution_failed",
        "message": "工具未执行",
    }
