from datetime import UTC, datetime

import pytest
import yaml

from app.agent_runtime.persistence.model import AgentRunMessage
from app.project_bundle.apply import BundleApplyConflictError, apply_project_bundle
from app.project_bundle.archive import build_zip, read_zip
from app.project_bundle.export import export_project_bundle
from app.project_bundle.importer import preview_project_bundle
from app.project_bundle.markdown import (
    parse_markdown_document,
    render_markdown_document,
)
from app.storage.models.character import Character
from app.storage.models.note import Note, NoteCategory
from app.storage.models.project import Project
from app.storage.models.task import Task
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry


def _rewrite_kind(bundle: bytes, kind: str, *, body: str) -> bytes:
    files = read_zip(bundle)
    manifest = yaml.safe_load(files["openfic.yaml"])
    item = next(item for item in manifest["documents"] if item["kind"] == kind)
    document = parse_markdown_document(files[item["path"]].decode())
    files[item["path"]] = render_markdown_document(
        document.frontmatter, document.title, body
    )
    return build_zip(files)


@pytest.mark.asyncio
async def test_apply_restores_all_supported_entities_as_safe_archives(session) -> None:
    project = Project(id="apply-project", title="应用项目")
    world = WorldInfo(id="apply-world", project_id=project.id, name="世界书")
    entry = WorldInfoEntry(
        id="apply-entry",
        world_info_id=world.id,
        uid=1,
        name="设定",
        section="基础",
        order=1,
        content="世界内容",
        is_enabled=False,
    )
    category = NoteCategory(
        id="apply-category", project_id=project.id, title="提纲", order=1
    )
    note = Note(
        id="apply-note",
        project_id=project.id,
        category_id=category.id,
        title="第一卷",
        order=1,
        content="提纲内容",
        is_locked=True,
        is_writing_visible=False,
    )
    character = Character(
        id="apply-character",
        project_id=project.id,
        name="角色",
        description="角色内容",
        order=1,
        is_favorited=True,
        is_writing_visible=False,
    )
    task = Task(
        id="apply-discussion",
        project_id=project.id,
        title="讨论",
        mode="agent",
        context_mode="global",
        agent_session_id="apply-session",
    )
    timestamp = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)
    message = AgentRunMessage(
        id="apply-message",
        session_id="apply-session",
        task_id=task.id,
        project_id=project.id,
        role="user",
        content="讨论内容",
        status="sent",
        display_channel="list",
        seq=0,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add_all([project, world, entry, category, note, character, task, message])
    await session.flush()
    bundle = await export_project_bundle(session, project.id)

    for row in (message, note, category, character, entry, task, world):
        await session.delete(row)
    await session.flush()

    result = await apply_project_bundle(session, project.id, bundle, "merge")
    assert result.summary["create"] == 6
    restored_entry = await session.get(WorldInfoEntry, entry.id)
    restored_character = await session.get(Character, character.id)
    restored_note = await session.get(Note, note.id)
    restored_task = await session.get(Task, task.id)
    restored_message = await session.get(AgentRunMessage, message.id)
    assert restored_entry is not None and restored_entry.is_enabled is False
    assert (
        restored_character is not None
        and restored_character.is_writing_visible is False
    )
    assert restored_note is not None and restored_note.is_locked is True
    assert restored_note.is_writing_visible is False
    assert restored_task is not None and restored_task.is_imported_archive is True
    assert restored_task.agent_session_id is None
    assert restored_task.context_mode == "global"
    assert restored_message is not None and restored_message.session_id == task.id
    assert restored_message.content == "讨论内容"

    verified = await preview_project_bundle(session, project.id, bundle, "merge")
    assert verified.summary == {
        "create": 0,
        "update": 0,
        "unchanged": 6,
        "conflict": 0,
    }
    assert read_zip(await export_project_bundle(session, project.id)) == read_zip(
        bundle
    )


@pytest.mark.asyncio
async def test_apply_updates_content_without_deleting_unlisted_rows(session) -> None:
    project = Project(id="apply-update-project", title="更新项目")
    note = Note(
        id="apply-update-note",
        project_id=project.id,
        title="待更新",
        content="基线",
        order=1,
    )
    session.add_all([project, note])
    await session.flush()
    edited = _rewrite_kind(
        await export_project_bundle(session, project.id), "note", body="导入后的内容"
    )

    extra = Note(
        id="apply-extra-note",
        project_id=project.id,
        title="Bundle 中不存在",
        content="必须保留",
        order=2,
    )
    session.add(extra)
    await session.flush()
    result = await apply_project_bundle(session, project.id, edited, "merge")

    assert result.summary["update"] == 1
    assert note.content == "导入后的内容"
    assert await session.get(Note, extra.id) is extra


@pytest.mark.asyncio
async def test_apply_rejects_updates_to_locked_notes(session) -> None:
    project = Project(id="apply-locked-project", title="锁定项目")
    note = Note(
        id="apply-locked-note",
        project_id=project.id,
        title="锁定笔记",
        content="基线",
        order=1,
    )
    session.add_all([project, note])
    await session.flush()
    edited = _rewrite_kind(
        await export_project_bundle(session, project.id),
        "note",
        body="导入后的内容",
    )
    note.is_locked = True
    await session.flush()

    with pytest.raises(BundleApplyConflictError) as conflict:
        await apply_project_bundle(session, project.id, edited, "merge")

    assert any(item.reason == "locked_note" for item in conflict.value.items)
    assert note.content == "基线"


@pytest.mark.asyncio
async def test_apply_rejects_concurrent_changes_and_live_discussion_edits(
    session,
) -> None:
    project = Project(id="apply-conflict-project", title="冲突项目")
    note = Note(
        id="apply-conflict-note",
        project_id=project.id,
        title="笔记",
        content="基线",
        order=1,
    )
    task = Task(
        id="apply-live-task",
        project_id=project.id,
        title="实时讨论",
        mode="agent",
        agent_session_id="apply-live-session",
    )
    message = AgentRunMessage(
        id="apply-live-message",
        session_id="apply-live-session",
        task_id=task.id,
        project_id=project.id,
        role="user",
        content="原讨论",
        status="sent",
        display_channel="list",
        seq=0,
    )
    session.add_all([project, note, task, message])
    await session.flush()
    baseline = await export_project_bundle(session, project.id)
    edited_note = _rewrite_kind(baseline, "note", body="Bundle 编辑")
    note.content = "数据库并发编辑"
    await session.flush()

    with pytest.raises(BundleApplyConflictError) as note_conflict:
        await apply_project_bundle(session, project.id, edited_note, "merge")
    assert note_conflict.value.items[0].reason == "current_changed"
    assert note.content == "数据库并发编辑"

    edited_message = _rewrite_kind(baseline, "discussion_message", body="改写讨论")
    with pytest.raises(BundleApplyConflictError) as discussion_conflict:
        await apply_project_bundle(session, project.id, edited_message, "merge")
    assert any(
        item.reason == "live_discussion_is_read_only"
        for item in discussion_conflict.value.items
    )
    assert message.content == "原讨论"


@pytest.mark.asyncio
async def test_apply_api_commits_and_returns_conflicts(session, client) -> None:
    project = Project(id="apply-api-project", title="API 项目")
    note = Note(
        id="apply-api-note",
        project_id=project.id,
        title="笔记",
        content="原文",
        order=1,
    )
    session.add_all([project, note])
    await session.flush()
    bundle = await export_project_bundle(session, project.id)
    edited = _rewrite_kind(bundle, "note", body="API 更新")

    response = await client.post(
        f"/api/v1/projects/{project.id}/bundle/import/apply",
        files={"file": ("bundle.zip", edited, "application/zip")},
        data={"mode": "merge"},
    )
    assert response.status_code == 200
    assert response.json()["summary"]["update"] == 1
    await session.refresh(note)
    assert note.content == "API 更新"

    note.content = "之后的数据库编辑"
    await session.commit()
    conflict = await client.post(
        f"/api/v1/projects/{project.id}/bundle/import/apply",
        files={"file": ("bundle.zip", edited, "application/zip")},
        data={"mode": "merge"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["conflicts"][0]["reason"] == "current_changed"
