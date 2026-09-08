"""Navigation management must not masquerade as document or message edits."""

from datetime import datetime

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_visibility import AgentVisibility
from app.storage.models.chapter import Chapter
from app.storage.models.character import Character
from app.storage.models.note import Note
from app.storage.models.project import Project
from app.storage.models.task import Task
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry
from app.storage.repos import chapter_repo
from app.storage.services import (
    character_service,
    note_service,
    project_folder_service,
    task_service,
    world_info_entry_service,
)

OLD = datetime(2020, 1, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["character", "world", "note", "outline", "discussion"])
async def test_management_preserves_time_and_noop_move_does_not_write(
    session: AsyncSession, scope: str
) -> None:
    project = Project(title="test")
    session.add(project)
    await session.flush()
    if scope == "character":
        item = Character(project_id=project.id, name="name", updated_at=OLD)
    elif scope == "world":
        world = WorldInfo(project_id=project.id, name="world")
        session.add(world)
        await session.flush()
        item = WorldInfoEntry(world_info_id=world.id, name="name", uid=1, order=1, updated_at=OLD)
    elif scope == "discussion":
        item = Task(project_id=project.id, title="name", mode="agent", updated_at=OLD)
    else:
        item = Note(project_id=project.id, title="name", document_type=scope, updated_at=OLD)
    session.add(item)
    await session.flush()

    writes = []
    connection = await session.connection()

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE")):
            writes.append(statement)

    event.listen(connection.sync_connection, "before_cursor_execute", capture)
    try:
        await project_folder_service.move_item(session, project.id, scope, item.id, None)
        assert writes == []
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", capture)

    folder = await project_folder_service.create_folder(session, project.id, scope, "folder")
    await project_folder_service.move_item(session, project.id, scope, item.id, folder.id)
    if scope == "character":
        await character_service.update_character(
            session, item.id, agent_visibility=AgentVisibility.NONE
        )
        await character_service.reorder_characters(session, project.id, [item.id])
    elif scope == "world":
        await world_info_entry_service.update_entry(
            session, item.id, agent_visibility=AgentVisibility.NONE
        )
    elif scope == "discussion":
        await task_service.update_task(session, item.id, title="renamed", is_favorited=True)
    else:
        await note_service.update_note(session, item.id, agent_visibility=AgentVisibility.NONE)
        await note_service.set_note_locked(session, item.id, True)
        await note_service.set_note_locked(session, item.id, False)
    await session.refresh(item)
    assert item.updated_at == OLD

    if scope == "character":
        await character_service.update_character(session, item.id, description="edited")
    elif scope == "world":
        await world_info_entry_service.update_entry(session, item.id, content="edited")
    elif scope != "discussion":
        await note_service.update_note(session, item.id, content="edited")
    else:
        await task_service.append_task_message(
            session,
            item.id,
            {
                "id": "new-message",
                "role": "user",
                "content": "hello",
                "created_at": datetime(2021, 1, 1),
            },
        )
    await session.refresh(item)
    assert item.updated_at > OLD


@pytest.mark.asyncio
async def test_chapter_reordering_preserves_content_time(session: AsyncSession) -> None:
    project = Project(title="test")
    session.add(project)
    await session.flush()
    chapters = [
        Chapter(project_id=project.id, title=str(i), order=i, updated_at=OLD) for i in (1, 2)
    ]
    session.add_all(chapters)
    await session.flush()
    await chapter_repo.update_orders(session, {chapters[0].id: 2, chapters[1].id: 1})
    for chapter in chapters:
        await session.refresh(chapter)
        assert chapter.updated_at == OLD
    assert [chapter.order for chapter in chapters] == [2, 1]


@pytest.mark.asyncio
async def test_runtime_message_advances_task_time(session: AsyncSession) -> None:
    from app.agent_runtime.persistence.repo import insert_message

    project = Project(title="test")
    session.add(project)
    await session.flush()
    task = Task(project_id=project.id, title="test", mode="agent", updated_at=OLD)
    session.add(task)
    await session.flush()
    await insert_message(
        session,
        session_id="test",
        task_id=task.id,
        project_id=project.id,
        role="assistant",
        status="done",
        content="reply",
        created_at=datetime(2021, 1, 1),
    )
    await session.refresh(task)
    assert task.updated_at == datetime(2021, 1, 1)
