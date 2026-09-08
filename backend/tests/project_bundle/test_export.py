import pytest
import yaml
from httpx import AsyncClient

from app.agent_runtime.persistence.model import AgentRunMessage
from app.project_bundle.archive import BundleFormatError, read_zip
from app.project_bundle.export import (
    document_semantic_hash,
    export_project_bundle,
    semantic_hash,
)
from app.project_bundle.markdown import parse_markdown_document
from app.storage.models.chapter import Chapter
from app.storage.models.character import Character
from app.storage.models.note import Note
from app.storage.models.project import Project
from app.storage.models.project_folder import ProjectFolder as NoteCategory
from app.storage.models.task import Task
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry


@pytest.mark.asyncio
async def test_export_structure_is_deterministic_and_filters_internal_messages(
    session, client: AsyncClient
) -> None:
    project = Project(id="bundle-project", title="测试项目", description="简介")
    other = Project(id="other-project", title="不应导出")
    world = WorldInfo(id="bundle-world", project_id=project.id, name="世界书")
    category = NoteCategory(scope="note", id="cat", project_id=project.id, title="设定", order=1)
    session.add_all(
        [
            project,
            other,
            world,
            category,
            WorldInfoEntry(
                id="entry",
                world_info_id=world.id,
                uid=1,
                name="规则",
                section="核心",
                order=1,
                content="内容",
            ),
            Character(
                id="character",
                project_id=project.id,
                name="角色",
                description="描述",
                order=1,
                image_path="secret.png",
            ),
            Character(
                id="other-character",
                project_id=other.id,
                name="跨项目角色",
                description="跨项目描述",
                order=1,
            ),
            Note(
                id="note",
                project_id=project.id,
                category_id=category.id,
                title="笔记",
                content="正文",
                order=1,
            ),
            NoteCategory(scope="note", id="empty", project_id=project.id, title="空分类", order=2),
            Task(
                id="task",
                project_id=project.id,
                title="讨论",
                mode="agent",
                agent_session_id="session",
                context_mode="global",
            ),
            AgentRunMessage(
                id="user",
                session_id="session",
                task_id="task",
                project_id=project.id,
                role="user",
                status="sent",
                seq=1,
                content="问题",
                message_metadata='{"attachments":[{"storage_name":"secret-path"}]}',
            ),
            AgentRunMessage(
                id="assistant",
                session_id="session",
                task_id="task",
                project_id=project.id,
                role="assistant",
                status="complete",
                seq=2,
                content="回答",
                reasoning="secret-reasoning",
                tool_calls='[{"args":{"api_key":"secret-tool-arg"}}]',
                message_metadata='{"private":"secret-metadata"}',
            ),
            AgentRunMessage(
                id="hidden",
                session_id="session",
                task_id="task",
                project_id=project.id,
                role="assistant",
                status="complete",
                seq=3,
                display_channel="hidden",
                content="不应导出",
            ),
            AgentRunMessage(
                id="tool",
                session_id="session",
                task_id="task",
                project_id=project.id,
                role="tool",
                status="complete",
                seq=4,
                content="secret-tool",
                message_metadata='{"api_key":"secret"}',
            ),
            AgentRunMessage(
                id="cross",
                session_id="session",
                task_id="task",
                project_id=other.id,
                role="assistant",
                status="complete",
                seq=5,
                content="跨项目",
            ),
        ]
    )
    await session.flush()

    first = await export_project_bundle(session, project.id)
    second = await export_project_bundle(session, project.id)
    assert first == second
    files = read_zip(first)
    manifest = yaml.safe_load(files["openfic.yaml"])
    assert manifest["schema"] == "openfic.project-bundle"
    assert manifest["version"] == 1
    assert manifest["project"] == {
        "id": project.id,
        "title": project.title,
        "description": project.description,
    }
    assert any(item["id"] == "empty" for item in manifest["note_categories"])
    decoded_bundle = "\n".join(data.decode("utf-8") for data in files.values())
    assert "secret" not in decoded_bundle
    assert "跨项目" not in decoded_bundle
    assert "other-character" not in decoded_bundle
    assert not any("secret" in path for path in files)
    message_files = [path for path in files if "/messages/" in path]
    assert len(message_files) == 2
    for path in message_files:
        parsed = parse_markdown_document(files[path].decode("utf-8"))
        assert set(parsed.frontmatter) == {
            "schema",
            "version",
            "kind",
            "id",
            "project_id",
            "discussion_id",
            "seq",
            "role",
            "status",
            "created_at",
            "updated_at",
            "base_hash",
        }
        assert parsed.frontmatter["kind"] == "discussion_message"
        assert parsed.frontmatter["discussion_id"] == "task"
    character_doc = parse_markdown_document(
        files[next(path for path in files if path.startswith("characters/"))].decode()
    )
    assert character_doc.title == "角色"
    assert character_doc.body == "描述"
    assert character_doc.frontmatter["agent_visibility"] == "all"
    assert "image_path" not in character_doc.frontmatter
    world_doc = parse_markdown_document(
        files[next(path for path in files if path.startswith("worldbook/"))].decode()
    )
    assert world_doc.title == "规则"
    assert world_doc.body == "内容"
    assert world_doc.frontmatter["section"] == "核心"
    assert world_doc.frontmatter["agent_visibility"] == "all"
    note_doc = parse_markdown_document(
        files[next(path for path in files if path.startswith("notes/"))].decode()
    )
    assert note_doc.title == "笔记"
    assert note_doc.body == "正文"
    discussion_doc = parse_markdown_document(
        files[next(path for path in files if path.endswith("/discussion.md"))].decode()
    )
    assert discussion_doc.frontmatter["context_mode"] == "global"
    documents_by_id = {item["id"]: item for item in manifest["documents"]}
    for item in manifest["documents"]:
        parsed = parse_markdown_document(files[item["path"]].decode())
        assert item["base_hash"] == parsed.frontmatter["base_hash"]
    assert set(documents_by_id) == {
        "entry",
        "character",
        "note",
        "task",
        "user",
        "assistant",
    }

    response = await client.get(f"/api/v1/projects/{project.id}/bundle/export")
    assert response.status_code == 200
    assert response.content == first
    disposition = response.headers["content-disposition"]
    assert 'filename="openfic-project-bundle.zip"' in disposition
    assert "filename*=UTF-8''" in disposition
    assert "测试项目" not in disposition


@pytest.mark.asyncio
async def test_export_accepts_flat_folders_and_rejects_missing_project(
    client: AsyncClient, session
) -> None:
    project = Project(id="cycle-project", title="环")
    session.add(project)
    await session.flush()
    session.add_all(
        [
            NoteCategory(scope="note", id="a", project_id=project.id, title="A", order=1),
            NoteCategory(scope="note", id="b", project_id=project.id, title="B", order=1),
        ]
    )
    await session.flush()
    assert await export_project_bundle(session, project.id)
    response = await client.get("/api/v1/projects/does-not-exist/bundle/export")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_export_places_outlines_in_their_own_directory(session) -> None:
    project = Project(id="outline-export", title="提纲导出")
    category = NoteCategory(
        id="outline-category",
        project_id=project.id,
        title="第一卷",
        scope="outline",
        order=1,
    )
    outline = Note(
        id="outline-note",
        project_id=project.id,
        category_id=category.id,
        title="开篇",
        document_type="outline",
        order=1,
    )
    session.add_all([project, category, outline])
    await session.flush()

    files = read_zip(await export_project_bundle(session, project.id))
    path = next(path for path in files if path.startswith("outlines/"))
    parsed = parse_markdown_document(files[path].decode())

    assert parsed.frontmatter["document_type"] == "outline"


@pytest.mark.asyncio
async def test_export_rejects_note_with_missing_category(session) -> None:
    project = Project(id="orphan-project", title="孤儿分类")
    session.add_all(
        [
            project,
            Note(
                id="orphan-note",
                project_id=project.id,
                category_id="missing-category",
                title="孤儿笔记",
                order=1,
            ),
        ]
    )
    await session.flush()

    with pytest.raises(BundleFormatError, match="note category is missing"):
        await export_project_bundle(session, project.id)


def test_semantic_hash_is_stable_and_changes_with_semantics() -> None:
    value = {"kind": "note", "title": "标题", "body": "正文"}
    assert semantic_hash(value) == semantic_hash(dict(value))
    assert semantic_hash(value) != semantic_hash({**value, "body": "新正文"})
    fields = {"kind": "note", "id": "n1", "project_id": "p1"}
    assert document_semantic_hash(fields, "标题", "正文") == document_semantic_hash(
        dict(fields), "标题", "正文"
    )
    assert document_semantic_hash(fields, "标题", "正文") != document_semantic_hash(
        fields, "标题", "新正文"
    )


@pytest.mark.asyncio
async def test_export_includes_writing_folders_and_root_chapters(session) -> None:
    project = Project(id="chapter-bundle", title="正文资料包")
    volume = NoteCategory(
        id="chapter-volume",
        project_id=project.id,
        scope="writing",
        title="第一卷",
        order=1,
    )
    root = Chapter(id="root-chapter", project_id=project.id, title="序章", order=1)
    nested = Chapter(
        id="nested-chapter",
        project_id=project.id,
        volume_id=volume.id,
        title="第一章",
        order=1,
    )
    session.add_all([project, volume, root, nested])
    await session.flush()

    files = read_zip(await export_project_bundle(session, project.id))
    manifest = yaml.safe_load(files["openfic.yaml"])
    documents = {item["id"]: item for item in manifest["documents"]}

    assert any(folder["id"] == volume.id for folder in manifest["project_folders"])
    assert documents[root.id]["path"].startswith("正文/")
    assert documents[nested.id]["path"].startswith("正文/第一卷/")
    root_document = parse_markdown_document(files[documents[root.id]["path"]].decode())
    assert root_document.frontmatter["volume_id"] is None
