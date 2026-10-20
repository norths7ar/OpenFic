"""Tests for Agent chapter and volume tools."""

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


def _make_volume(
    *,
    volume_id: str = "vol-1",
    order: int = 1,
    title: str = "第一卷",
    description: str | None = None,
    chapter_count: int = 2,
):
    volume = MagicMock()
    volume.id = volume_id
    volume.project_id = "proj-1"
    volume.order = order
    volume.title = title
    volume.description = description
    volume.item_count = chapter_count
    return volume


def _assert_success_payload(result: str, tool_name: str) -> dict:
    data = json.loads(result)
    assert data["type"] == "ok"
    assert data["success"] is True
    assert data["tool_name"] == tool_name
    assert data["revision_id"] == "rev-1"
    return data


async def test_create_volume_builds_approval_preview() -> None:
    from app.agent_runtime.tools.impls.chapter.create_volume import CreateVolumeTool

    runtime_session = AsyncMock()
    tool = CreateVolumeTool(_state=_make_state())
    object.__setattr__(tool, "_config", {"configurable": {"db_session": runtime_session}})

    with patch(
        "app.agent_runtime.tools.impls.chapter.create_volume.volume_repo.get_max_order",
        AsyncMock(return_value=2),
    ):
        preview = await tool.build_interrupt_preview({"title": "第三卷", "description": "终局"})

    assert preview == {
        "type": "preview",
        "success": True,
        "reason": "approval_preview",
        "metadata": {
            "volume": {
                "order": 3,
                "title": "第三卷",
                "description": "终局",
                "chapter_count": 0,
            }
        },
    }


async def test_edit_volume_builds_approval_preview() -> None:
    from app.agent_runtime.tools.impls.chapter.edit_volume import EditVolumeTool

    runtime_session = AsyncMock()
    volume = _make_volume(title="旧卷", description="旧描述")
    tool = EditVolumeTool(_state=_make_state())
    object.__setattr__(tool, "_config", {"configurable": {"db_session": runtime_session}})

    with patch(
        "app.agent_runtime.tools.impls.chapter.edit_volume.volume_repo.list_by_project",
        AsyncMock(return_value=[volume]),
    ):
        preview = await tool.build_interrupt_preview(
            {
                "volume_ref": {"type": "title", "value": "旧卷"},
                "new_title": "新卷",
                "new_description": "新描述",
            }
        )

    assert preview == {
        "type": "preview",
        "success": True,
        "reason": "approval_preview",
        "metadata": {
            "volume": {
                "order": 1,
                "title": "新卷",
                "description": "新描述",
                "chapter_count": 2,
            }
        },
    }
