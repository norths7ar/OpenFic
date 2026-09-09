"""Recovery behavior at the common SQLite mutation boundary."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select, update

from app.core.errors import ConflictError
from app.storage.history_capture import history_source
from app.storage.models.chapter import Chapter
from app.storage.models.character import Character
from app.storage.models.document_history import DocumentHistory, DocumentTrash
from app.storage.models.note import Note
from app.storage.models.project import Project
from app.storage.models.project_folder import ProjectFolder
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry
from app.storage.services import document_history_service as service


async def document(session, kind):
    project = Project(title="Recovery")
    session.add(project)
    await session.flush()
    folder = ProjectFolder(project_id=project.id, scope=service.SCOPES[kind], title="Folder")
    session.add(folder)
    await session.flush()
    if kind == "world_entry":
        world = WorldInfo(project_id=project.id, name="World")
        session.add(world)
        await session.flush()
        item = WorldInfoEntry(
            world_info_id=world.id,
            folder_id=folder.id,
            uid=1,
            order=1,
            name="Before",
            content="Original",
        )
    elif kind == "character":
        item = Character(
            project_id=project.id, folder_id=folder.id, name="Before", description="Original"
        )
    elif kind == "chapter":
        item = Chapter(
            project_id=project.id, volume_id=folder.id, order=1, title="Before", content="Original"
        )
    else:
        item = Note(
            project_id=project.id,
            category_id=folder.id,
            document_type=kind,
            title="Before",
            content="Original",
        )
    session.add(item)
    await session.flush()
    return project, folder, item


def edit(item, title, content):
    setattr(item, "name" if isinstance(item, (Character, WorldInfoEntry)) else "title", title)
    setattr(item, "description" if isinstance(item, Character) else "content", content)
    item.updated_at = datetime.now(UTC)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", list(service.MODELS))
async def test_history_restore_and_undo_for_every_kind(session, kind):
    project, _, item = await document(session, kind)
    edit(item, "After", "Changed")
    await session.flush()
    versions, base = await service.history_list(session, project.id, kind, item.id)
    assert [(v.title, v.content, v.source) for v in versions] == [("Before", "Original", "manual")]
    await service.restore_history(session, project.id, kind, item.id, versions[0].id, base)
    versions, base = await service.history_list(session, project.id, kind, item.id)
    assert (versions[0].title, versions[0].content, versions[0].source) == (
        "After",
        "Changed",
        "restore",
    )
    await service.restore_history(session, project.id, kind, item.id, versions[0].id, base)
    assert getattr(item, "description" if kind == "character" else "content") == "Changed"


@pytest.mark.asyncio
async def test_manual_grouping_ai_boundaries_noop_and_cap(session):
    project, _, item = await document(session, "note")
    for text in ("one", "two", "three"):
        edit(item, "Before", text)
        await session.flush()
    versions, _ = await service.history_list(session, project.id, "note", item.id)
    assert len(versions) == 1
    with history_source("ai"):
        edit(item, "Before", "AI")
        await session.flush()
        edit(item, "Before", "AI")
        await session.flush()
    versions, _ = await service.history_list(session, project.id, "note", item.id)
    assert len(versions) == 2
    assert versions[0].source == "ai"
    edit(item, "Before", "user again")
    await session.flush()
    versions, _ = await service.history_list(session, project.id, "note", item.id)
    assert len(versions) == 3
    versions[0].created_at = datetime.now(UTC) - timedelta(minutes=6)
    await session.flush()
    edit(item, "Before", "new interval")
    await session.flush()
    with history_source("ai"):
        for index in range(105):
            edit(item, "Before", str(index))
            await session.flush()
    versions, _ = await service.history_list(session, project.id, "note", item.id)
    assert len(versions) == 100


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", list(service.MODELS))
@pytest.mark.parametrize("missing_folder", [False, True])
async def test_bulk_delete_trash_restores_metadata_and_history(session, kind, missing_folder):
    project, folder, item = await document(session, kind)
    edit(item, "After", "Changed")
    await session.flush()
    item_id = item.id
    await session.execute(delete(type(item)).where(type(item).id == item_id))
    if missing_folder:
        await session.delete(folder)
        await session.flush()
    trash = await service.trash_list(session, project.id)
    assert len(trash) == 1
    restored_id, restored_kind = await service.restore_trash(session, project.id, trash[0].id)
    assert (restored_id, restored_kind) == (item_id, kind)
    restored = await service.get_document(session, project.id, kind, item_id)
    assert getattr(restored, service.FOLDERS[kind]) == (None if missing_folder else folder.id)
    assert getattr(restored, "description" if kind == "character" else "content") == "Changed"
    versions, _ = await service.history_list(session, project.id, kind, item_id)
    assert len(versions) == 1
    assert await service.trash_list(session, project.id) == []


@pytest.mark.asyncio
async def test_stale_restore_and_permanent_cleanup(session):
    project, _, item = await document(session, "note")
    edit(item, "After", "Changed")
    await session.flush()
    versions, base = await service.history_list(session, project.id, "note", item.id)
    edit(item, "Latest", "Newer")
    await session.flush()
    with pytest.raises(ConflictError):
        await service.restore_history(session, project.id, "note", item.id, versions[0].id, base)
    await session.delete(item)
    await session.flush()
    trash = await service.trash_list(session, project.id)
    await service.delete_trash(session, project.id, trash[0].id)
    assert (await session.execute(select(DocumentHistory))).scalars().all() == []
    assert (await session.execute(select(DocumentTrash))).scalars().all() == []


@pytest.mark.asyncio
async def test_bulk_import_capture_and_project_cleanup(session):
    project, _, item = await document(session, "note")
    with history_source("import"):
        await session.execute(
            update(Note).where(Note.id == item.id).values(title="Imported", content="New")
        )
    versions, _ = await service.history_list(session, project.id, "note", item.id)
    assert versions[0].source == "import"
    await session.execute(delete(Note).where(Note.id == item.id))
    await session.delete(project)
    await session.flush()
    assert (await session.execute(select(DocumentHistory))).scalars().all() == []
    assert (await session.execute(select(DocumentTrash))).scalars().all() == []


@pytest.mark.asyncio
async def test_task_cleanup_does_not_remove_history(session):
    from app.storage.models.task import Task
    from app.storage.services.task_service import delete_task

    project, _, item = await document(session, "note")
    task = Task(project_id=project.id, title="Disposable task", mode="agent")
    session.add(task)
    edit(item, "After", "Changed")
    await session.flush()
    await delete_task(session, task.id)
    versions, _ = await service.history_list(session, project.id, "note", item.id)
    assert len(versions) == 1


@pytest.mark.asyncio
async def test_real_agent_tool_execution_keeps_recovery_after_task_deletion(session, monkeypatch):
    import json
    from unittest.mock import AsyncMock

    from app.agent_runtime.tools.impls.chapter.edit_chapter import EditChapterTool
    from app.storage.models.revision import Revision
    from app.storage.models.task import Task
    from app.storage.services.task_service import delete_task

    project, folder, chapter = await document(session, "chapter")
    task = Task(project_id=project.id, title="Agent", mode="agent")
    session.add(task)
    await session.flush()
    revision = Revision(
        project_id=project.id, task_id=task.id, message="Edit", project_snapshot_title=project.title
    )
    session.add(revision)
    await session.flush()
    tool = EditChapterTool(
        _state={
            "project_id": project.id,
            "task_id": task.id,
            "session_id": "history-test",
            "current_revision_id": revision.id,
        }
    )
    monkeypatch.setattr(
        "app.agent_runtime.tools.impls.chapter.edit_chapter.create_session",
        AsyncMock(return_value=session),
    )
    monkeypatch.setattr(session, "close", AsyncMock())
    monkeypatch.setattr("app.background.jobs.service.commit_and_notify", AsyncMock())
    result = json.loads(
        await tool.ainvoke(
            {
                "volume_ref": {"type": "title", "value": folder.title},
                "chapter_ref": {"type": "order", "value": 1},
                "new_title": "AI title",
            }
        )
    )
    assert result["success"] is True
    versions, _ = await service.history_list(session, project.id, "chapter", chapter.id)
    assert [(v.title, v.source) for v in versions] == [("Before", "ai")]
    await delete_task(session, task.id)
    versions, _ = await service.history_list(session, project.id, "chapter", chapter.id)
    assert len(versions) == 1


@pytest.mark.asyncio
async def test_character_image_is_preserved_until_permanent_commit(session, monkeypatch):
    from unittest.mock import Mock

    from app.storage.services.character_service import delete_character

    project, _, item = await document(session, "character")
    item.image_path = "recovery-image.png"
    await session.flush()
    cleanup = Mock()
    monkeypatch.setattr("app.core.storage.delete_character_image", cleanup)
    await delete_character(session, item.id)
    trash = await service.trash_list(session, project.id)
    cleanup.assert_not_called()
    await service.delete_trash(session, project.id, trash[0].id)
    cleanup.assert_not_called()
    await session.commit()
    cleanup.assert_called_once_with("recovery-image.png")


@pytest.mark.asyncio
async def test_image_cleanup_is_discarded_on_rollback(session, monkeypatch):
    from unittest.mock import Mock

    cleanup = Mock()
    monkeypatch.setattr("app.core.storage.delete_character_image", cleanup)
    await session.execute(select(Project))
    service.schedule_image_cleanup(session, ["do-not-remove.png"])
    await session.rollback()
    await session.commit()
    cleanup.assert_not_called()
