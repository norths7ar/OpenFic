import pytest
import yaml

from app.agent_runtime.persistence.model import AgentRunMessage
from app.project_bundle.archive import BundleFormatError, build_zip, read_zip
from app.project_bundle.export import export_project_bundle
from app.project_bundle.importer import parse_project_bundle, preview_project_bundle
from app.project_bundle.markdown import (
    parse_markdown_document,
    render_markdown_document,
)
from app.storage.models.note import Note, NoteCategory
from app.storage.models.project import Project
from app.storage.models.task import Task
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry


def _rewrite_document(bundle: bytes, *, body: str) -> bytes:
    files = read_zip(bundle)
    path = next(path for path in files if path.endswith(".md"))
    document = parse_markdown_document(files[path].decode())
    files[path] = render_markdown_document(document.frontmatter, document.title, body)
    return build_zip(files)


def _rewrite_manifest(bundle: bytes, mutate) -> bytes:
    files = read_zip(bundle)
    manifest = yaml.safe_load(files["openfic.yaml"])
    mutate(manifest)
    files["openfic.yaml"] = yaml.safe_dump(manifest, allow_unicode=True, sort_keys=True)
    return build_zip(files)


@pytest.mark.asyncio
async def test_export_then_preview_is_unchanged_and_edit_is_update(session) -> None:
    project = Project(id="import-project", title="导入项目")
    note = Note(
        id="import-note", project_id=project.id, title="笔记", content="原文", order=1
    )
    session.add_all([project, note])
    await session.flush()
    bundle = await export_project_bundle(session, project.id)
    parsed = parse_project_bundle(bundle, project.id)
    assert parsed.documents[0].base_hash
    unchanged = await preview_project_bundle(session, project.id, bundle, "merge")
    assert unchanged.summary["unchanged"] == 1
    edited_bundle = _rewrite_document(bundle, body="编辑后的正文")
    updated = await preview_project_bundle(session, project.id, edited_bundle, "merge")
    assert updated.summary["update"] == 1


@pytest.mark.asyncio
async def test_preview_modes_and_no_write(session) -> None:
    project = Project(id="mode-project", title="模式项目")
    session.add(project)
    await session.flush()
    bundle = await export_project_bundle(session, project.id)
    preview = await preview_project_bundle(session, project.id, bundle, "append")
    assert preview.summary == {"create": 0, "update": 0, "unchanged": 0, "conflict": 0}
    assert await session.get(Note, "missing") is None


@pytest.mark.asyncio
async def test_preview_modes_and_concurrent_change_rules(session) -> None:
    project = Project(id="mode-rules-project", title="模式规则")
    note = Note(
        id="mode-note",
        project_id=project.id,
        title="笔记",
        content="基线",
        order=1,
    )
    session.add_all([project, note])
    await session.flush()
    bundle = await export_project_bundle(session, project.id)
    edited = _rewrite_document(bundle, body="作者编辑")

    append = await preview_project_bundle(session, project.id, edited, "append")
    update = await preview_project_bundle(session, project.id, edited, "update")
    merge = await preview_project_bundle(session, project.id, edited, "merge")
    assert append.items[0].action == "conflict"
    assert update.items[0].action == "update"
    assert merge.items[0].action == "update"

    note.content = "数据库并发编辑"
    await session.flush()
    concurrent = await preview_project_bundle(session, project.id, edited, "merge")
    assert concurrent.items[0].action == "conflict"
    assert concurrent.items[0].reason == "current_changed"

    unchanged_source = await preview_project_bundle(
        session, project.id, bundle, "merge"
    )
    assert unchanged_source.items[0].action == "unchanged"
    assert unchanged_source.items[0].reason == "incoming_matches_base"

    await session.delete(note)
    await session.flush()
    missing_append = await preview_project_bundle(session, project.id, bundle, "append")
    missing_update = await preview_project_bundle(session, project.id, bundle, "update")
    missing_merge = await preview_project_bundle(session, project.id, bundle, "merge")
    assert missing_append.items[0].action == "create"
    assert missing_update.items[0].reason == "missing_for_update"
    assert missing_merge.items[0].action == "create"


@pytest.mark.asyncio
async def test_category_edit_and_cross_project_id_are_previewed(session) -> None:
    target = Project(id="category-target", title="目标")
    other = Project(id="category-other", title="其他")
    category = NoteCategory(
        id="category-edit", project_id=target.id, title="旧分类", order=1
    )
    note = Note(
        id="cross-note",
        project_id=target.id,
        title="跨项目测试",
        content="正文",
        order=1,
    )
    session.add_all([target, other, category, note])
    await session.flush()
    bundle = await export_project_bundle(session, target.id)
    edited_category = _rewrite_manifest(
        bundle,
        lambda manifest: manifest["note_categories"][0].update(title="新分类"),
    )
    category_preview = await preview_project_bundle(
        session, target.id, edited_category, "merge"
    )
    category_item = next(
        item for item in category_preview.items if item.kind == "note_category"
    )
    assert category_item.action == "update"

    note.project_id = other.id
    await session.flush()
    cross_preview = await preview_project_bundle(session, target.id, bundle, "merge")
    cross_item = next(item for item in cross_preview.items if item.id == note.id)
    assert cross_item.action == "conflict"
    assert cross_item.reason == "cross_project_id"


@pytest.mark.asyncio
async def test_preview_rejects_same_name_with_different_id(session) -> None:
    project = Project(id="name-conflict-project", title="重名项目")
    incoming = Note(
        id="incoming-note",
        project_id=project.id,
        title="同名笔记",
        content="待导入",
        order=1,
    )
    session.add_all([project, incoming])
    await session.flush()
    bundle = await export_project_bundle(session, project.id)

    await session.delete(incoming)
    session.add(
        Note(
            id="existing-note",
            project_id=project.id,
            title="同名笔记",
            content="数据库现有内容",
            order=1,
        )
    )
    await session.flush()

    preview = await preview_project_bundle(session, project.id, bundle, "merge")
    item = next(item for item in preview.items if item.id == "incoming-note")
    assert item.action == "conflict"
    assert item.reason == "same_name_different_id"


@pytest.mark.asyncio
async def test_parser_rejects_identity_tampering_and_unlisted_files(session) -> None:
    project = Project(id="tamper-project", title="篡改")
    note = Note(
        id="tamper-note", project_id=project.id, title="笔记", content="正文", order=1
    )
    session.add_all([project, note])
    await session.flush()
    bundle = await export_project_bundle(session, project.id)

    mismatched = _rewrite_manifest(
        bundle,
        lambda manifest: manifest["documents"][0].update(
            base_hash="sha256:" + "0" * 64
        ),
    )
    with pytest.raises(BundleFormatError, match="identity mismatch"):
        parse_project_bundle(mismatched, project.id)

    files = read_zip(bundle)
    files["extra.md"] = "未列文件"
    with pytest.raises(BundleFormatError, match="unlisted"):
        parse_project_bundle(build_zip(files), project.id)

    other = Project(id="tamper-other", title="其他")
    session.add(other)
    await session.flush()
    with pytest.raises(BundleFormatError, match="does not match"):
        parse_project_bundle(bundle, other.id)


@pytest.mark.asyncio
async def test_parser_rejects_orphan_category_and_discussion_message(session) -> None:
    project = Project(id="orphan-import-project", title="孤儿")
    note = Note(
        id="orphan-import-note",
        project_id=project.id,
        title="笔记",
        content="正文",
        order=1,
    )
    session.add_all([project, note])
    await session.flush()
    bundle = await export_project_bundle(session, project.id)
    files = read_zip(bundle)
    note_path = next(path for path in files if path.endswith(".md"))
    document = parse_markdown_document(files[note_path].decode())
    document.frontmatter["category_id"] = "missing-category"
    files[note_path] = render_markdown_document(
        document.frontmatter, document.title, document.body
    )
    with pytest.raises(BundleFormatError, match="note category is missing"):
        parse_project_bundle(build_zip(files), project.id)

    task = Task(
        id="orphan-discussion",
        project_id=project.id,
        title="讨论",
        mode="agent",
        agent_session_id="orphan-session",
    )
    message = AgentRunMessage(
        id="orphan-message",
        session_id="orphan-session",
        task_id=task.id,
        project_id=project.id,
        role="user",
        status="sent",
        seq=0,
        content="问题",
    )
    session.add_all([task, message])
    await session.flush()
    discussion_bundle = await export_project_bundle(session, project.id)
    discussion_files = read_zip(discussion_bundle)
    manifest = yaml.safe_load(discussion_files["openfic.yaml"])
    discussion_item = next(
        item for item in manifest["documents"] if item["kind"] == "discussion"
    )
    message_item = next(
        item for item in manifest["documents"] if item["kind"] == "discussion_message"
    )

    invalid_discussion_files = dict(discussion_files)
    discussion_doc = parse_markdown_document(
        invalid_discussion_files[discussion_item["path"]].decode()
    )
    invalid_discussion_files[discussion_item["path"]] = render_markdown_document(
        discussion_doc.frontmatter, discussion_doc.title, "不应写在讨论元数据正文"
    )
    with pytest.raises(BundleFormatError, match="body must be empty"):
        parse_project_bundle(build_zip(invalid_discussion_files), project.id)

    invalid_message_files = dict(discussion_files)
    message_doc = parse_markdown_document(
        invalid_message_files[message_item["path"]].decode()
    )
    invalid_message_files[message_item["path"]] = render_markdown_document(
        message_doc.frontmatter, "被改坏的消息标题", message_doc.body
    )
    with pytest.raises(BundleFormatError, match="H1 is not canonical"):
        parse_project_bundle(build_zip(invalid_message_files), project.id)

    invalid_time_files = dict(discussion_files)
    time_doc = parse_markdown_document(
        invalid_time_files[message_item["path"]].decode()
    )
    time_doc.frontmatter["created_at"] = "2026-01-02T03:04:05"
    invalid_time_files[message_item["path"]] = render_markdown_document(
        time_doc.frontmatter, time_doc.title, time_doc.body
    )
    with pytest.raises(BundleFormatError, match="include a timezone"):
        parse_project_bundle(build_zip(invalid_time_files), project.id)

    pending_files = dict(discussion_files)
    pending_doc = parse_markdown_document(pending_files[message_item["path"]].decode())
    pending_doc.frontmatter["status"] = "pending"
    pending_files[message_item["path"]] = render_markdown_document(
        pending_doc.frontmatter, pending_doc.title, pending_doc.body
    )
    with pytest.raises(BundleFormatError, match="pending discussion"):
        parse_project_bundle(build_zip(pending_files), project.id)

    manifest["documents"] = [
        item for item in manifest["documents"] if item is not discussion_item
    ]
    del discussion_files[discussion_item["path"]]
    discussion_files["openfic.yaml"] = yaml.safe_dump(
        manifest, allow_unicode=True, sort_keys=True
    )
    with pytest.raises(BundleFormatError, match="message parent is missing"):
        parse_project_bundle(build_zip(discussion_files), project.id)


@pytest.mark.asyncio
async def test_parser_and_preview_reject_internal_and_world_book_collisions(
    session,
) -> None:
    target = Project(id="bundle-collision-target", title="目标")
    other = Project(id="bundle-collision-other", title="其他")
    target_world = WorldInfo(
        id="bundle-target-world", project_id=target.id, name="目标世界书"
    )
    other_world = WorldInfo(
        id="bundle-other-world", project_id=other.id, name="其他世界书"
    )
    entry = WorldInfoEntry(
        id="bundle-collision-entry",
        world_info_id=target_world.id,
        uid=1,
        name="设定",
        order=1,
    )
    first_category = NoteCategory(
        id="bundle-category-a", project_id=target.id, title="分类甲", order=1
    )
    second_category = NoteCategory(
        id="bundle-category-b", project_id=target.id, title="分类乙", order=2
    )
    session.add_all(
        [
            target,
            other,
            target_world,
            other_world,
            entry,
            first_category,
            second_category,
        ]
    )
    await session.flush()
    bundle = await export_project_bundle(session, target.id)

    duplicate_categories = _rewrite_manifest(
        bundle,
        lambda manifest: manifest["note_categories"][1].update(title="分类甲"),
    )
    with pytest.raises(BundleFormatError, match="duplicated among siblings"):
        parse_project_bundle(duplicate_categories, target.id)

    files = read_zip(bundle)
    manifest = yaml.safe_load(files["openfic.yaml"])
    world_item = next(
        item for item in manifest["documents"] if item["kind"] == "world_entry"
    )
    world_doc = parse_markdown_document(files[world_item["path"]].decode())
    world_doc.frontmatter["world_info_id"] = other_world.id
    files[world_item["path"]] = render_markdown_document(
        world_doc.frontmatter, world_doc.title, world_doc.body
    )
    preview = await preview_project_bundle(
        session, target.id, build_zip(files), "merge"
    )
    entry_item = next(item for item in preview.items if item.id == entry.id)
    assert entry_item.action == "conflict"
    assert entry_item.reason == "cross_project_world_book_id"


@pytest.mark.asyncio
async def test_preview_api_validates_input_and_does_not_write(
    session, client, monkeypatch
) -> None:
    project = Project(id="api-import-project", title="API 导入")
    session.add(project)
    await session.flush()
    bundle = await export_project_bundle(session, project.id)

    response = await client.post(
        f"/api/v1/projects/{project.id}/bundle/import/preview",
        files={"file": ("bundle.zip", bundle, "application/zip")},
        data={"mode": "merge"},
    )
    assert response.status_code == 200
    assert response.json()["summary"] == {
        "create": 0,
        "update": 0,
        "unchanged": 0,
        "conflict": 0,
    }
    assert await session.get(Project, project.id) is not None

    empty = await client.post(
        f"/api/v1/projects/{project.id}/bundle/import/preview",
        files={"file": ("empty.zip", b"", "application/zip")},
    )
    assert empty.status_code == 400
    missing = await client.post(
        "/api/v1/projects/missing/bundle/import/preview",
        files={"file": ("bundle.zip", bundle, "application/zip")},
    )
    assert missing.status_code == 404
    invalid_mode = await client.post(
        f"/api/v1/projects/{project.id}/bundle/import/preview",
        files={"file": ("bundle.zip", bundle, "application/zip")},
        data={"mode": "replace"},
    )
    assert invalid_mode.status_code == 400

    monkeypatch.setattr("app.api.routers.project_bundles.MAX_BUNDLE_UPLOAD_BYTES", 1)
    oversized = await client.post(
        f"/api/v1/projects/{project.id}/bundle/import/preview",
        files={"file": ("bundle.zip", b"12", "application/zip")},
    )
    assert oversized.status_code == 413


@pytest.mark.asyncio
async def test_archive_task_messages_are_projected_and_exported(
    session, client
) -> None:
    project = Project(id="archive-project", title="档案项目")
    other_project = Project(id="archive-other-project", title="其他项目")
    task = Task(
        id="archive-task",
        project_id=project.id,
        title="历史讨论",
        mode="agent",
        is_imported_archive=True,
        agent_session_id=None,
    )
    message = AgentRunMessage(
        id="archive-message",
        session_id="historical-session",
        task_id=task.id,
        project_id=project.id,
        role="user",
        content="历史内容",
        status="completed",
        display_channel="list",
        seq=0,
    )
    cross_project_message = AgentRunMessage(
        id="archive-cross-project-message",
        session_id="historical-session",
        task_id=task.id,
        project_id=other_project.id,
        role="user",
        content="不应泄露",
        status="completed",
        display_channel="list",
        seq=1,
    )
    session.add_all([project, other_project, task, message, cross_project_message])
    await session.flush()

    response = await client.get(f"/api/v1/tasks/{task.id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["is_imported_archive"] is True
    assert payload["agent_session_id"] is None
    assert len(payload["messages"]) == 1
    assert payload["messages"][0]["content"] == "历史内容"

    bundle = await export_project_bundle(session, project.id)
    parsed = parse_project_bundle(bundle, project.id)
    assert {doc.id for doc in parsed.documents} >= {task.id, message.id}
    preview = await preview_project_bundle(session, project.id, bundle, "merge")
    assert preview.summary == {
        "create": 0,
        "update": 0,
        "unchanged": 2,
        "conflict": 0,
    }
