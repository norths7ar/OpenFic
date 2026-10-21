"""MessagePersister.finalize 测试 — 中断场景。"""

import json

import pytest
from langchain_core.messages import AIMessageChunk
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.persistence import repo
from app.agent_runtime.persistence.persister import MessagePersister


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
