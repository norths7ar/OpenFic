"""Tests for Agent note tools."""

import json
from unittest.mock import AsyncMock, MagicMock, patch


def _make_state() -> dict:
    return {
        "session_id": "sess-1",
        "task_id": "task-1",
        "project_id": "proj-1",
        "model_config": {},
        "active_agent": None,
        "is_completed": False,
        "error": None,
        "retry_count": 0,
        "message_checkpoints": [],
        "user_request": "",
        "current_revision_id": "rev-1",
    }


def _make_note(
    *,
    note_id: str = "note-1",
    title: str = "测试笔记",
    content: str = "测试内容",
    is_locked: bool = False,
    agent_visibility: str = "all",
    project_id: str = "proj-1",
    category_id: str | None = None,
):
    note = MagicMock()
    note.id = note_id
    note.project_id = project_id
    note.category_id = category_id
    note.title = title
    note.content = content
    note.is_locked = is_locked
    note.agent_visibility = agent_visibility
    note.created_at = None
    note.updated_at = None
    return note


async def test_read_note_rejects_hidden_note() -> None:
    from app.agent_runtime.tools.impls.note.read_note import ReadNoteTool

    note = _make_note(note_id="note-1", title="隐藏", agent_visibility="none")
    tool = ReadNoteTool(_state=_make_state())

    with patch("app.agent_runtime.tools.impls.note.read_note.create_session") as mock_cs:
        mock_session = AsyncMock()
        mock_cs.return_value = mock_session
        with patch(
            "app.agent_runtime.tools.impls.note.read_note.note_repo.get_by_id",
            AsyncMock(return_value=note),
        ):
            result = await tool.ainvoke({"note_ref": {"id": "note-1"}})
            mock_session.close.assert_called_once()

    data = json.loads(result)
    assert data["type"] == "fail"
    assert "已隐藏" in data["message"]
