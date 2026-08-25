import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.agent_runtime.agents.definitions import get_default_agent_definition
from app.agent_runtime.agents.tool_categories import (
    TOOL_CATEGORIES,
    TOOL_CATEGORY_DISPLAY,
)
from app.agent_runtime.tools.impls.project_change import (
    ProposeProjectChangeInput,
    ProposeProjectChangeTool,
)
from app.agent_runtime.tools.permission_metadata import get_default_tool_permission_mode


def _state(**overrides: object) -> dict:
    state = {
        "session_id": "session-1",
        "task_id": "task-1",
        "project_id": "project-a",
        "current_message_id": "message-1",
        "model_config": {"model_id": "model-a"},
    }
    state.update(overrides)
    return state


def test_project_change_tool_is_registered_for_discuss_with_allow_permission() -> None:
    discuss = get_default_agent_definition("discuss")

    assert "project_change_proposal" in discuss.enabled_tool_categories
    assert TOOL_CATEGORIES["project_change_proposal"] == ("propose_project_change",)
    assert TOOL_CATEGORY_DISPLAY["project_change_proposal"]
    assert get_default_tool_permission_mode("propose_project_change") == "allow"
    assert ProposeProjectChangeTool.model_fields["access_level"].default == "write"


@pytest.mark.parametrize(
    "payload",
    [
        {"target_type": "note", "operation": "create", "target_id": "n1", "after": {}},
        {"target_type": "note", "operation": "create", "after": None},
        {"target_type": "note", "operation": "update", "after": {}},
        {"target_type": "note", "operation": "delete", "target_id": "n1", "after": {}},
    ],
)
def test_project_change_input_validates_operation_shape(payload: dict) -> None:
    with pytest.raises(ValidationError):
        ProposeProjectChangeInput.model_validate(payload)


@pytest.mark.asyncio
async def test_project_change_creates_pending_record_without_writing_formal_material() -> (
    None
):
    tool = ProposeProjectChangeTool(_state=_state())
    db_session = AsyncMock()
    change = SimpleNamespace(
        id="change-1",
        project_id="project-a",
        target_type="note",
        target_id=None,
        operation="create",
        status="pending",
        base_hash=None,
        before=None,
        after={"kind": "note", "title": "新笔记", "body": "正文"},
        source_task_id="task-1",
        source_message_id="message-1",
        model_id="model-a",
    )

    with (
        patch(
            "app.agent_runtime.tools.impls.project_change.create_session",
            return_value=db_session,
        ),
        patch(
            "app.agent_runtime.tools.impls.project_change.pending_project_change_service.create_pending_change",
            new=AsyncMock(return_value=change),
        ) as create_change,
    ):
        result = await tool.ainvoke(
            {
                "target_type": "note",
                "operation": "create",
                "after": {"title": "新笔记", "body": "正文"},
            }
        )

    payload = json.loads(result)
    assert payload["success"] is True
    assert payload["pending_change_id"] == "change-1"
    assert payload["pending_change"]["status"] == "pending"
    create_change.assert_awaited_once_with(
        db_session,
        project_id="project-a",
        target_type="note",
        target_id=None,
        operation="create",
        after={"title": "新笔记", "body": "正文"},
        source_task_id="task-1",
        source_message_id="message-1",
        model_id="model-a",
    )
    db_session.commit.assert_awaited_once()
    db_session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_project_change_uses_state_project_and_rejects_missing_project() -> None:
    tool = ProposeProjectChangeTool(_state=_state(project_id=None))

    result = await tool.ainvoke(
        {
            "target_type": "note",
            "operation": "create",
            "after": {"title": "新笔记"},
        }
    )

    assert "缺少当前项目" in json.loads(result)["error"]


@pytest.mark.asyncio
async def test_project_change_preserves_project_isolation() -> None:
    tool = ProposeProjectChangeTool(_state=_state(project_id="project-b"))
    db_session = AsyncMock()
    change = SimpleNamespace(
        id="change-2",
        project_id="project-b",
        target_type="character",
        target_id="char-b",
        operation="update",
        status="pending",
        base_hash="sha256:base",
        before={"id": "char-b"},
        after={"id": "char-b", "title": "新名", "body": "描述"},
        source_task_id=None,
        source_message_id=None,
        model_id=None,
    )

    with (
        patch(
            "app.agent_runtime.tools.impls.project_change.create_session",
            return_value=db_session,
        ),
        patch(
            "app.agent_runtime.tools.impls.project_change.pending_project_change_service.create_pending_change",
            new=AsyncMock(return_value=change),
        ) as create_change,
    ):
        await tool.ainvoke(
            {
                "target_type": "character",
                "target_id": "char-b",
                "operation": "update",
                "after": {"title": "新名", "body": "描述"},
            }
        )

    assert create_change.await_args.kwargs["project_id"] == "project-b"
