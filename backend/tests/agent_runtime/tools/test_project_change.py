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
    ProposeProjectCreateInput,
    ProposeProjectCreateTool,
    ProposeProjectDeleteTool,
    ProposeProjectUpdateInput,
    ProposeProjectUpdateTool,
)
from app.agent_runtime.tools.permission_metadata import get_default_tool_permission_mode

PROPOSAL_TOOL_NAMES = (
    "propose_project_create",
    "propose_project_update",
    "propose_project_delete",
)


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


def _change(**overrides: object) -> SimpleNamespace:
    values = {
        "id": "change-1",
        "project_id": "project-a",
        "target_type": "note",
        "target_id": "note-1",
        "operation": "update",
        "status": "pending",
        "base_hash": "sha256:base",
        "before": {"kind": "note", "id": "note-1", "body": "原正文"},
        "after": {"kind": "note", "id": "note-1", "body": "新正文"},
        "source_task_id": "task-1",
        "source_message_id": "message-1",
        "model_id": "model-a",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_project_change_tools_are_registered_for_discuss_with_allow_permission() -> None:
    discuss = get_default_agent_definition("discuss")

    assert "project_change_proposal" in discuss.enabled_tool_categories
    assert TOOL_CATEGORIES["project_change_proposal"] == PROPOSAL_TOOL_NAMES
    assert TOOL_CATEGORY_DISPLAY["project_change_proposal"]
    for tool_name in PROPOSAL_TOOL_NAMES:
        assert get_default_tool_permission_mode(tool_name) == "allow"


def test_update_schema_exposes_only_mutable_fields() -> None:
    properties = ProposeProjectUpdateInput.model_json_schema()["properties"]

    assert set(properties) == {
        "target_type",
        "target_id",
        "title",
        "body",
        "agent_visibility",
        "section",
    }
    assert {
        "kind",
        "category_id",
        "document_type",
        "order",
        "project_id",
        "is_locked",
        "is_hidden",
    }.isdisjoint(properties)


@pytest.mark.parametrize(
    "payload",
    [
        {"target_type": "note", "target_id": "note-1"},
        {"target_type": "note", "target_id": "note-1", "title": None},
        {
            "target_type": "note",
            "target_id": "note-1",
            "section": "不适用",
        },
        {
            "target_type": "note_category",
            "target_id": "category-1",
            "body": "不适用",
        },
    ],
)
def test_update_input_rejects_empty_null_or_target_incompatible_patches(
    payload: dict,
) -> None:
    with pytest.raises(ValidationError):
        ProposeProjectUpdateInput.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"target_type": "character", "title": "角色", "category_id": "category-1"},
        {"target_type": "character", "title": "角色", "document_type": "outline"},
        {"target_type": "note", "title": "笔记", "section": "不适用"},
        {"target_type": "note_category", "title": "分类", "body": "不适用"},
    ],
)
def test_create_input_rejects_target_incompatible_fields(payload: dict) -> None:
    with pytest.raises(ValidationError):
        ProposeProjectCreateInput.model_validate(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("target_type", ["world_entry", "character", "note", "note_category"])
async def test_create_accepts_explicit_defaults_without_leaking_target_fields(
    target_type: str,
) -> None:
    defaults = {
        "body": "",
        "agent_visibility": "all",
        "category_id": None,
        "document_type": "note",
        "section": "",
    }
    values = {"target_type": target_type, "title": "新资料"}
    if target_type != "note_category":
        values.update(body="正文", agent_visibility="global")
    if target_type == "world_entry":
        values["section"] = "人外种族"
    with patch(
        "app.agent_runtime.tools.impls.project_change._queue_pending_change",
        new=AsyncMock(return_value='{"success":true}'),
    ) as queue:
        tool = ProposeProjectCreateTool(_state=_state())
        await tool.ainvoke(values)
        expected = queue.await_args.kwargs
        queue.reset_mock()
        result = await tool.ainvoke({**defaults, **values})
        assert json.loads(result)["success"] is True
        queue.assert_awaited_once()
        assert queue.await_args.kwargs == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "placeholders",
    [
        {},
        {"title": None, "agent_visibility": None, "section": None},
        {"title": None, "agent_visibility": None, "section": ""},
    ],
)
async def test_project_update_sends_only_requested_patch_fields(placeholders: dict) -> None:
    tool = ProposeProjectUpdateTool(_state=_state())
    db_session = AsyncMock()
    change = _change()

    with (
        patch(
            "app.agent_runtime.tools.impls.project_change.create_session",
            return_value=db_session,
        ),
        patch(
            "app.agent_runtime.tools.impls.project_change.pending_project_change_apply_service._resolve_snapshot",
            new=AsyncMock(return_value=(None, {"agent_visibility": "all"})),
        ),
        patch(
            "app.agent_runtime.tools.impls.project_change.pending_project_change_service.create_pending_change",
            new=AsyncMock(return_value=change),
        ) as create_change,
    ):
        result = await tool.ainvoke(
            {
                "target_type": "note",
                "target_id": "note-1",
                "body": "新正文",
                **placeholders,
            }
        )

    payload = json.loads(result)
    assert payload["success"] is True
    create_change.assert_awaited_once_with(
        db_session,
        project_id="project-a",
        target_type="note",
        target_id="note-1",
        operation="update",
        after={"body": "新正文"},
        source_task_id="task-1",
        source_message_id="message-1",
        model_id="model-a",
    )
    db_session.commit.assert_awaited_once()
    db_session.close.assert_awaited_once()


@pytest.mark.parametrize("target_type", ["character", "note", "world_entry", "note_category"])
def test_update_null_placeholders_preserve_target_rules(target_type: str) -> None:
    payload = {
        "target_type": target_type,
        "target_id": "item-1",
        "title": "新标题",
        "body": None,
        "section": None,
        "agent_visibility": None,
    }
    assert ProposeProjectUpdateInput.model_validate(payload).title == "新标题"
    with pytest.raises(ValidationError, match="至少要提供"):
        ProposeProjectUpdateInput.model_validate({**payload, "title": None})


def test_world_update_preserves_explicit_empty_body_and_section() -> None:
    proposal = ProposeProjectUpdateInput.model_validate(
        {"target_type": "world_entry", "target_id": "entry-1", "body": "", "section": ""}
    )
    assert proposal.body == ""
    assert proposal.section == ""


@pytest.mark.asyncio
async def test_project_create_builds_target_specific_payload() -> None:
    tool = ProposeProjectCreateTool(_state=_state())
    db_session = AsyncMock()
    change = _change(
        target_id=None,
        operation="create",
        base_hash=None,
        before=None,
        after={"kind": "note", "title": "新提纲"},
    )

    with (
        patch(
            "app.agent_runtime.tools.impls.project_change.create_session",
            return_value=db_session,
        ),
        patch(
            "app.agent_runtime.tools.impls.project_change.pending_project_change_apply_service._resolve_snapshot",
            new=AsyncMock(return_value=(None, {"agent_visibility": "all"})),
        ),
        patch(
            "app.agent_runtime.tools.impls.project_change.pending_project_change_service.create_pending_change",
            new=AsyncMock(return_value=change),
        ) as create_change,
    ):
        await tool.ainvoke(
            {
                "target_type": "note",
                "title": "新提纲",
                "body": "正文",
                "category_id": "category-1",
                "document_type": "outline",
                "agent_visibility": "global",
            }
        )

    create_change.assert_awaited_once_with(
        db_session,
        project_id="project-a",
        target_type="note",
        target_id=None,
        operation="create",
        after={
            "title": "新提纲",
            "body": "正文",
            "category_id": "category-1",
            "agent_visibility": "global",
            "document_type": "outline",
        },
        source_task_id="task-1",
        source_message_id="message-1",
        model_id="model-a",
    )


@pytest.mark.asyncio
async def test_project_delete_uses_server_snapshot_without_after_payload() -> None:
    tool = ProposeProjectDeleteTool(_state=_state())
    db_session = AsyncMock()
    change = _change(operation="delete", after=None)

    with (
        patch(
            "app.agent_runtime.tools.impls.project_change.create_session",
            return_value=db_session,
        ),
        patch(
            "app.agent_runtime.tools.impls.project_change.pending_project_change_apply_service._resolve_snapshot",
            new=AsyncMock(return_value=(None, {"agent_visibility": "all"})),
        ),
        patch(
            "app.agent_runtime.tools.impls.project_change.pending_project_change_service.create_pending_change",
            new=AsyncMock(return_value=change),
        ) as create_change,
    ):
        await tool.ainvoke({"target_type": "note", "target_id": "note-1"})

    assert create_change.await_args.kwargs["operation"] == "delete"
    assert create_change.await_args.kwargs["after"] is None


@pytest.mark.asyncio
async def test_project_change_rejects_missing_project() -> None:
    tool = ProposeProjectUpdateTool(_state=_state(project_id=None))

    result = await tool.ainvoke({"target_type": "note", "target_id": "note-1", "body": "新正文"})

    payload = json.loads(result)
    assert payload["type"] == "fail"
    assert payload["success"] is False
    assert "缺少当前项目" in payload["message"]
