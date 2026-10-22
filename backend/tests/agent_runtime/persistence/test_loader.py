"""load_history 测试。"""

from pathlib import Path

import pytest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.attachments import (
    build_image_content_blocks,
)
from app.agent_runtime.persistence import repo
from app.agent_runtime.persistence.errors import PersistenceLoadError
from app.agent_runtime.persistence.loader import load_history


@pytest.mark.asyncio
async def test_load_history_basic_roles_in_seq_order(db_session: AsyncSession, sample_task):
    sid = "session_a"
    await repo.insert_message(
        db_session,
        session_id=sid,
        task_id=sample_task.id,
        project_id=sample_task.project_id,
        role="system",
        content="sys",
        status="complete",
    )
    await repo.insert_message(
        db_session,
        session_id=sid,
        task_id=sample_task.id,
        project_id=sample_task.project_id,
        role="user",
        content="hi",
        status="sent",
    )
    await repo.insert_message(
        db_session,
        session_id=sid,
        task_id=sample_task.id,
        project_id=sample_task.project_id,
        role="assistant",
        content="hello back",
        status="complete",
    )

    msgs = await load_history(db_session, sid)
    assert len(msgs) == 3
    assert isinstance(msgs[0], SystemMessage) and msgs[0].content == "sys"
    assert isinstance(msgs[1], HumanMessage) and msgs[1].content == "hi"
    assert isinstance(msgs[2], AIMessage) and msgs[2].content == "hello back"


@pytest.mark.asyncio
async def test_build_image_content_blocks_reads_server_attachment_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.settings import settings

    monkeypatch.setattr(settings, "agent_attachments_dir", tmp_path)
    attachment_path = tmp_path / "session-1" / "reference.png"
    attachment_path.parent.mkdir()
    attachment_path.write_bytes(b"image-data")

    blocks = await build_image_content_blocks(
        [
            {
                "storage_name": "session-1/reference.png",
                "mime_type": "image/png",
            }
        ]
    )

    assert blocks == [{"type": "image", "base64": "aW1hZ2UtZGF0YQ==", "mime_type": "image/png"}]


@pytest.mark.asyncio
async def test_load_history_pairs_assistant_with_tool(db_session: AsyncSession, sample_task):
    sid = "session_a"
    await repo.insert_message(
        db_session,
        session_id=sid,
        task_id=sample_task.id,
        project_id=sample_task.project_id,
        role="assistant",
        content="",
        status="complete",
        tool_calls=[{"id": "c1", "name": "read_chapter", "args": {"order": 1}}],
    )
    await repo.insert_message(
        db_session,
        session_id=sid,
        task_id=sample_task.id,
        project_id=sample_task.project_id,
        role="tool",
        content="chapter body",
        status="complete",
        tool_call_id="c1",
        tool_name="read_chapter",
    )
    msgs = await load_history(db_session, sid)
    assert len(msgs) == 2
    assert isinstance(msgs[0], AIMessage)
    assert len(msgs[0].tool_calls) == 1
    tc0 = msgs[0].tool_calls[0]
    assert tc0["id"] == "c1"
    assert tc0["name"] == "read_chapter"
    assert tc0["args"] == {"order": 1}
    assert isinstance(msgs[1], ToolMessage)
    assert msgs[1].tool_call_id == "c1"


class _BrokenSession:
    async def execute(self, *_a, **_kw):
        raise RuntimeError("DB down")

    async def commit(self):
        raise RuntimeError("DB down")

    async def rollback(self):
        return None

    async def close(self):
        return None

    def add(self, *_a, **_kw):
        return None

    async def get(self, *_a, **_kw):
        raise RuntimeError("DB down")

    async def refresh(self, *_a, **_kw):
        return None


@pytest.mark.asyncio
async def test_load_history_propagates_load_error():
    with pytest.raises(PersistenceLoadError):
        await load_history(_BrokenSession(), "session_a")  # type: ignore[arg-type]
