"""note_service 服务层测试。"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.storage.models.note import Note
from app.storage.models.project import Project
from app.storage.repos import note_repo
from app.storage.services import note_service


async def _create_project(session: AsyncSession) -> Project:
    project = Project(title="测试项目", description="")
    session.add(project)
    await session.flush()
    return project


@pytest.mark.asyncio
async def test_locked_note_blocks_content_move_and_delete_but_allows_visibility(
    session: AsyncSession,
) -> None:
    project = await _create_project(session)
    target = await note_service.create_category(session, project.id, parent_id=None, title="目标")
    note = await note_service.create_note(
        session, project.id, category_id=None, title="锁定笔记", content="原文"
    )
    await note_service.set_note_locked(session, note.id, True)

    with pytest.raises(ConflictError, match="已锁定"):
        await note_service.update_note(session, note.id, content="改写")
    with pytest.raises(ConflictError, match="已锁定"):
        await note_service.move_item(session, "note", note.id, target.id)
    with pytest.raises(ConflictError, match="已锁定"):
        await note_service.delete_note(session, note.id)

    updated = await note_service.update_note(session, note.id, agent_visibility="global")
    assert updated.agent_visibility == "global"


@pytest.mark.asyncio
async def test_hidden_notes_not_returned_in_list_notes_tool_mode(
    session: AsyncSession,
) -> None:
    project = await _create_project(session)
    hidden_note = Note(
        project_id=project.id,
        category_id=None,
        title="隐藏笔记",
        content="",
        agent_visibility="none",
    )
    session.add(hidden_note)
    await session.flush()
    visible_notes = await note_repo.list_by_project(session, project.id, include_hidden=False)
    assert all(n.agent_visibility != "none" for n in visible_notes)
