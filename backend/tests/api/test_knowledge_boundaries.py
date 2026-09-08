import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.agent_runtime.context.helpers import compile_canonical_mentions
from app.agent_runtime.tools.errors import ToolExecutionError
from app.agent_runtime.tools.impls.context.character import (
    _list_project_characters,
)
from app.agent_runtime.tools.impls.context.world_entry import (
    _resolve_enabled_entry_by_title,
)
from app.agent_runtime.tools.impls.note.edit_note import EditNoteTool
from app.agent_runtime.tools.impls.note.read_note import ReadNoteTool
from app.core.knowledge_scope import KnowledgeScope
from app.storage.models.character import Character
from app.storage.models.note import Note
from app.storage.models.project import Project
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry
from tests.api.test_agent import _SESSION_RUNNERS, _seed_agent_target


@pytest.mark.asyncio
async def test_build_rejects_global_context(client: AsyncClient) -> None:
    target = await _seed_agent_target(client)

    response = await client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": target["project_id"],
            "model_id": target["model_id"],
            "context_mode": "global",
            "agent_key": "build",
        },
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_global_discuss_session_cannot_switch_to_build_on_message(
    client: AsyncClient,
) -> None:
    target = await _seed_agent_target(client)
    created = await client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": target["project_id"],
            "model_id": target["model_id"],
            "context_mode": "global",
            "agent_key": "discuss",
        },
    )
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    with patch("app.api.routers.agent_runtime._launch_task", AsyncMock()):
        response = await client.post(
            f"/api/v1/agent/sessions/{session_id}/message",
            json={"message": "继续讨论", "agent_key": "build"},
        )

    assert response.status_code == 400
    assert _SESSION_RUNNERS[session_id].agent_key == "discuss"


@pytest.mark.asyncio
async def test_local_visibility_filters_character_and_world_entry_but_global_allows(
    session,
) -> None:
    project = Project(id="knowledge-boundary-project", title="知识边界")
    visible = Character(
        id="visible-character",
        project_id=project.id,
        name="可见人物",
        agent_visibility="all",
    )
    hidden = Character(
        id="hidden-character",
        project_id=project.id,
        name="隐藏人物",
        agent_visibility="global",
    )
    world = WorldInfo(id="knowledge-boundary-world", project_id=project.id, name="世界书")
    disabled = WorldInfoEntry(
        id="disabled-world-entry",
        world_info_id=world.id,
        uid=1,
        order=1,
        name="隐藏设定",
        agent_visibility="global",
    )
    session.add_all([project, visible, hidden, world, disabled])
    await session.commit()

    local = await _list_project_characters(session, project.id, scope=KnowledgeScope.LOCAL)
    global_ = await _list_project_characters(session, project.id, scope=KnowledgeScope.GLOBAL)
    assert [item.name for item in local] == ["可见人物"]
    assert {item.name for item in global_} == {"可见人物", "隐藏人物"}

    with pytest.raises(ToolExecutionError):
        await _resolve_enabled_entry_by_title(
            session, world.id, "隐藏设定", scope=KnowledgeScope.LOCAL
        )
    resolved = await _resolve_enabled_entry_by_title(
        session, world.id, "隐藏设定", scope=KnowledgeScope.GLOBAL
    )
    assert resolved.id == disabled.id


@pytest.mark.asyncio
async def test_note_read_and_edit_preview_follow_local_global_boundary(
    session, monkeypatch
) -> None:
    project = Project(id="note-boundary-project", title="笔记边界")
    note = Note(
        id="note-boundary-hidden",
        project_id=project.id,
        title="隐藏笔记",
        content="旧正文",
        agent_visibility="global",
    )
    session.add_all([project, note])
    await session.commit()

    class SessionProxy:
        def __getattr__(self, name):
            return getattr(session, name)

        async def close(self):
            return None

    proxy = SessionProxy()
    monkeypatch.setattr(
        "app.agent_runtime.tools.impls.note.read_note.create_session",
        AsyncMock(return_value=proxy),
    )
    monkeypatch.setattr(
        "app.agent_runtime.tools.impls.note.edit_note.create_session",
        AsyncMock(return_value=proxy),
    )

    local_reader = ReadNoteTool(_state={"project_id": project.id, "context_mode": "local"})
    with pytest.raises(ToolExecutionError):
        await local_reader._execute({"id": note.id})
    global_reader = ReadNoteTool(_state={"project_id": project.id, "context_mode": "global"})
    assert json.loads(await global_reader._execute({"id": note.id}))["content"] == "旧正文"

    local_editor = EditNoteTool(_state={"project_id": project.id, "context_mode": "local"})
    object.__setattr__(
        local_editor,
        "_config",
        {"configurable": {"db_session": session}},
    )
    assert (
        await local_editor.build_interrupt_preview(
            {
                "note_ref": {"id": note.id},
                "old_content": "旧正文",
                "new_content": "新正文",
            }
        )
        is None
    )
    global_editor = EditNoteTool(_state={"project_id": project.id, "context_mode": "global"})
    object.__setattr__(
        global_editor,
        "_config",
        {"configurable": {"db_session": session}},
    )
    preview = await global_editor.build_interrupt_preview(
        {
            "note_ref": {"id": note.id},
            "old_content": "旧正文",
            "new_content": "新正文",
        }
    )
    assert preview is not None


@pytest.mark.asyncio
async def test_expanded_mentions_drop_hidden_body_in_local_but_compile_global(
    session,
) -> None:
    project = Project(id="expanded-boundary-project", title="展开提及")
    character = Character(
        id="expanded-hidden-character",
        project_id=project.id,
        name="隐藏人物",
        description="不应泄漏的正文",
        agent_visibility="global",
    )
    note = Note(
        id="expanded-hidden-note",
        project_id=project.id,
        title="隐藏笔记",
        content="不应泄漏的笔记正文",
        agent_visibility="global",
    )
    world = WorldInfo(id="expanded-boundary-world", project_id=project.id, name="世界书")
    entry = WorldInfoEntry(
        id="expanded-hidden-entry",
        world_info_id=world.id,
        uid=1,
        order=1,
        name="隐藏设定",
        content="不应泄漏的世界书正文",
        agent_visibility="global",
    )
    session.add_all([project, character, note, world, entry])
    await session.commit()
    source = (
        '<of-mention character_id="expanded-hidden-character" '
        'line_start="1" line_end="1">人物正文</of-mention>'
        '<of-mention note_id="expanded-hidden-note" '
        'line_start="1" line_end="1">笔记正文</of-mention>'
        '<of-mention world_info_entry_id="expanded-hidden-entry" '
        'line_start="1" line_end="1">世界书正文</of-mention>'
    )

    local = await compile_canonical_mentions(source, session, project.id, context_mode="local")
    global_ = await compile_canonical_mentions(source, session, project.id, context_mode="global")
    assert "人物正文" not in local
    assert "笔记正文" not in local
    assert "世界书正文" not in local
    assert "人物正文" in global_
    assert "笔记正文" in global_
    assert "世界书正文" in global_
