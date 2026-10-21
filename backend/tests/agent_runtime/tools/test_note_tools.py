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


def _make_category(
    *,
    category_id: str = "cat-1",
    title: str = "分类A",
    parent_id: str | None = None,
    project_id: str = "proj-1",
    scope: str = "note",
):
    cat = MagicMock()
    cat.id = category_id
    cat.project_id = project_id
    cat.parent_id = parent_id
    cat.title = title
    cat.scope = scope
    return cat


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


async def test_edit_note_rejects_locked_note() -> None:
    from app.agent_runtime.tools.impls.note.edit_note import EditNoteTool

    note = _make_note(note_id="note-1", title="锁定笔记", is_locked=True, content="旧内容")
    tool = EditNoteTool(_state=_make_state())

    with patch("app.agent_runtime.tools.impls.note.edit_note.create_session") as mock_cs:
        mock_session = AsyncMock()
        mock_cs.return_value = mock_session
        with patch(
            "app.agent_runtime.tools.impls.note.edit_note.note_repo.get_by_id",
            AsyncMock(return_value=note),
        ):
            result = await tool.ainvoke(
                {
                    "note_ref": {"id": "note-1"},
                    "old_content": "旧内容",
                    "new_content": "新内容",
                }
            )
            mock_session.close.assert_called_once()

    data = json.loads(result)
    assert data["type"] == "fail"
    assert "已锁定" in data["message"]


async def test_delete_note_rejects_hidden_note() -> None:
    from app.agent_runtime.tools.impls.note.delete_note import DeleteNoteTool

    note = _make_note(note_id="note-1", title="隐藏笔记", agent_visibility="none")
    tool = DeleteNoteTool(_state=_make_state())

    with patch("app.agent_runtime.tools.impls.note.delete_note.create_session") as mock_cs:
        mock_session = AsyncMock()
        mock_cs.return_value = mock_session
        with patch(
            "app.agent_runtime.tools.impls.note.delete_note.note_repo.get_by_id",
            AsyncMock(return_value=note),
        ):
            result = await tool.ainvoke({"note_ref": {"id": "note-1"}})
            mock_session.close.assert_called_once()

    data = json.loads(result)
    assert data["type"] == "fail"
    assert "已隐藏" in data["message"]


async def test_delete_note_rejects_locked_note() -> None:
    from app.agent_runtime.tools.impls.note.delete_note import DeleteNoteTool

    note = _make_note(note_id="note-1", title="锁定笔记", is_locked=True)
    tool = DeleteNoteTool(_state=_make_state())

    with patch("app.agent_runtime.tools.impls.note.delete_note.create_session") as mock_cs:
        mock_session = AsyncMock()
        mock_cs.return_value = mock_session
        with patch(
            "app.agent_runtime.tools.impls.note.delete_note.note_repo.get_by_id",
            AsyncMock(return_value=note),
        ):
            result = await tool.ainvoke({"note_ref": {"id": "note-1"}})
            mock_session.close.assert_called_once()

    data = json.loads(result)
    assert data["type"] == "fail"
    assert "已锁定" in data["message"]


async def test_move_note_rejects_locked_note() -> None:
    from app.agent_runtime.tools.impls.note.move_note import MoveNoteTool

    note = _make_note(note_id="note-1", title="锁定笔记", is_locked=True)
    tool = MoveNoteTool(_state=_make_state())

    with patch("app.agent_runtime.tools.impls.note.move_note.create_session") as mock_cs:
        mock_session = AsyncMock()
        mock_cs.return_value = mock_session
        with patch(
            "app.agent_runtime.tools.impls.note.move_note.note_repo.get_by_id",
            AsyncMock(return_value=note),
        ):
            result = await tool.ainvoke({"note_ref": {"id": "note-1"}, "target_category_ref": None})
            mock_session.close.assert_called_once()

    data = json.loads(result)
    assert data["type"] == "fail"
    assert "已锁定" in data["message"]


async def test_edit_note_category_rejects_category_from_another_project() -> None:
    from app.agent_runtime.tools.impls.note.edit_note_category import EditNoteCategoryTool

    tool = EditNoteCategoryTool(_state=_make_state())
    category = _make_category(project_id="proj-other")

    with patch("app.agent_runtime.tools.impls.note.edit_note_category.create_session") as mock_cs:
        mock_session = AsyncMock()
        mock_cs.return_value = mock_session
        with patch(
            "app.agent_runtime.tools.impls.note.edit_note_category.note_category_repo.get_by_id",
            AsyncMock(return_value=category),
        ):
            result = await tool.ainvoke({"category_ref": {"id": "cat-1"}, "new_title": "新分类"})

    assert json.loads(result)["message"] == "分类不属于当前项目或笔记范围"


async def test_delete_note_category_rejects_category_from_another_project() -> None:
    from app.agent_runtime.tools.impls.note.delete_note_category import (
        DeleteNoteCategoryTool,
    )

    tool = DeleteNoteCategoryTool(_state=_make_state())
    category = _make_category(project_id="proj-other")

    with patch("app.agent_runtime.tools.impls.note.delete_note_category.create_session") as mock_cs:
        mock_session = AsyncMock()
        mock_cs.return_value = mock_session
        with patch(
            "app.agent_runtime.tools.impls.note.delete_note_category.note_category_repo.get_by_id",
            AsyncMock(return_value=category),
        ):
            result = await tool.ainvoke({"category_ref": {"id": "cat-1"}})

    assert json.loads(result)["message"] == "分类不属于当前项目"
