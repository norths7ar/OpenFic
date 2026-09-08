from unittest.mock import AsyncMock, patch

import pytest
import yaml

from app.project_bundle.apply import BundleApplyConflictError, apply_project_bundle
from app.project_bundle.archive import BundleFormatError, build_zip, read_zip
from app.project_bundle.export import export_project_bundle
from app.project_bundle.importer import parse_project_bundle, preview_project_bundle
from app.project_bundle.mapped_bundle import build_mapped_project_bundle
from app.project_bundle.markdown import parse_markdown_document, render_markdown_document
from app.project_bundle.source_export import export_markdown_source_bundle
from app.project_bundle.source_mapping import parse_source_mapping
from app.storage.models.chapter import Chapter
from app.storage.models.project import Project
from app.storage.models.project_folder import ProjectFolder


async def _seed_chapters(session) -> tuple[Project, ProjectFolder, Chapter, Chapter]:
    project = Project(id="chapter-roundtrip", title="正文往返")
    volume = ProjectFolder(
        id="chapter-volume", project_id=project.id, scope="writing", title="第一卷", order=1
    )
    root = Chapter(
        id="chapter-root",
        project_id=project.id,
        title="序章",
        content="根目录第一行\n根目录第二行",
        order=1,
    )
    nested = Chapter(
        id="chapter-nested",
        project_id=project.id,
        volume_id=volume.id,
        title="第一章",
        content="卷内正文",
        order=2,
    )
    session.add_all([project, volume, root, nested])
    await session.flush()
    return project, volume, root, nested


@pytest.mark.asyncio
async def test_native_chapter_bundle_round_trip_preserves_empty_volume_root_and_order(
    session,
) -> None:
    project, volume, root, nested = await _seed_chapters(session)
    empty = ProjectFolder(
        id="chapter-empty-volume",
        project_id=project.id,
        scope="writing",
        title="空卷",
        order=2,
    )
    session.add(empty)
    await session.flush()
    data = await export_project_bundle(session, project.id)
    parsed = parse_project_bundle(data, project.id)

    chapters = {
        document.id: document for document in parsed.documents if document.kind == "chapter"
    }
    assert chapters[root.id].semantic_fields["volume_id"] is None
    assert chapters[root.id].body == "根目录第一行\n根目录第二行"
    assert chapters[nested.id].semantic_fields["volume_id"] == volume.id
    assert chapters[nested.id].semantic_fields["order"] == 2
    assert {folder.id for folder in parsed.project_folders} >= {volume.id, empty.id}

    await session.delete(root)
    await session.delete(nested)
    await session.flush()
    await session.delete(volume)
    await session.delete(empty)
    await session.flush()
    with (
        patch(
            "app.retrieval.chapter_index.ChapterIndexIntegrationService.mark_chapter_stale_if_changed",
            AsyncMock(),
        ) as mark_stale,
        patch("app.retrieval.chapter_index.safe_maybe_enqueue_auto_index", AsyncMock()) as enqueue,
        patch("app.retrieval.index_status.schedule_emit_index_status") as emit_status,
    ):
        result = await apply_project_bundle(session, project.id, data, "append")
    assert result.summary["create"] == 4
    assert mark_stale.await_count == 2
    enqueue.assert_awaited_once_with(session, project_id=project.id)
    emit_status.assert_called_once_with(session, project.id)
    unchanged = await preview_project_bundle(session, project.id, data, "merge")
    assert unchanged.summary == {"create": 0, "update": 0, "unchanged": 4, "conflict": 0}


@pytest.mark.asyncio
async def test_source_chapter_round_trip_keeps_stable_ids_after_file_and_title_rename(
    session,
) -> None:
    project, volume, root, nested = await _seed_chapters(session)
    source = await export_markdown_source_bundle(session, project.id)
    files = read_zip(source)
    config = yaml.safe_load(files["openfic-import.yaml"])
    rule = next(rule for rule in config["rules"] if rule["target"] == "chapters")
    assert rule["glob"] == "正文/*.md"
    old_path = next(path for path, value in files.items() if f"id: {nested.id}\n" in value.decode())
    new_path = "正文/第一卷/改名后的文件.md"
    document = files.pop(old_path).decode()
    files[new_path] = document.replace("# 第一章", "# 改名后的章节", 1).replace(
        "卷内正文", "正文第一行\n\n正文第二行", 1
    )

    mapped_items = parse_source_mapping(build_zip(files), project.id)
    mapped = {item.target_id: item for item in mapped_items if item.target == "chapters"}
    assert mapped[nested.id].title == "改名后的章节"
    assert mapped[nested.id].body == "正文第一行\n\n正文第二行"
    assert mapped[nested.id].category_target_ids == [volume.id]
    assert mapped[root.id].category_target_ids == []

    native = await build_mapped_project_bundle(session, project.id, build_zip(files))
    parsed = parse_project_bundle(native.data, project.id)
    chapter = next(document for document in parsed.documents if document.id == nested.id)
    assert chapter.title == "改名后的章节"
    assert chapter.body == "正文第一行\n\n正文第二行"
    assert chapter.semantic_fields["volume_id"] == volume.id
    assert chapter.semantic_fields["order"] == nested.order


@pytest.mark.asyncio
async def test_chapter_bundle_detects_three_way_content_conflict_and_cross_project_id(
    session,
) -> None:
    project, _volume, _root, nested = await _seed_chapters(session)
    data = await export_project_bundle(session, project.id)
    files = read_zip(data)
    manifest = yaml.safe_load(files["openfic.yaml"])
    item = next(entry for entry in manifest["documents"] if entry["id"] == nested.id)
    document = files[item["path"]].decode()
    files[item["path"]] = document.rsplit("\n", 1)[0].replace("卷内正文", "外部修改") + "\n"
    incoming = build_zip(files)
    nested.content = "OpenFic 内部修改"
    await session.flush()

    preview = await preview_project_bundle(session, project.id, incoming, "merge")
    conflict = next(item for item in preview.items if item.id == nested.id)
    assert conflict.action == "conflict"
    assert conflict.reason == "current_changed"
    with pytest.raises(BundleApplyConflictError):
        await apply_project_bundle(session, project.id, incoming, "merge")

    foreign = Project(id="chapter-foreign", title="外部")
    session.add(foreign)
    await session.flush()
    nested.project_id = foreign.id
    await session.flush()
    preview = await preview_project_bundle(session, project.id, data, "merge")
    assert next(item for item in preview.items if item.id == nested.id).reason == "cross_project_id"


@pytest.mark.asyncio
async def test_chapter_exports_make_same_and_invalid_titles_safe_and_distinct(session) -> None:
    project, volume, _root, nested = await _seed_chapters(session)
    duplicate = Chapter(
        id="chapter-duplicate",
        project_id=project.id,
        volume_id=volume.id,
        title=nested.title,
        content="保留第一行\n保留第二行",
        order=3,
    )
    unsafe = Chapter(
        id="chapter-unsafe",
        project_id=project.id,
        title="CON:/非法",
        content="正文",
        order=2,
    )
    session.add_all([duplicate, unsafe])
    await session.flush()

    native = read_zip(await export_project_bundle(session, project.id))
    source = read_zip(await export_markdown_source_bundle(session, project.id))

    native_paths = [path for path in native if path.startswith("正文/")]
    assert len(native_paths) == len(set(native_paths))
    assert all("CON:" not in path and ":" not in path for path in native_paths)
    assert "正文/序章.md" in native_paths
    assert f"正文/第一卷/第一章--{nested.id}.md" in native_paths
    assert f"正文/第一卷/第一章--{duplicate.id}.md" in native_paths
    source_paths = [path for path in source if path.startswith("正文/")]
    assert len(source_paths) == len(set(source_paths))
    assert "正文/序章.md" in source_paths
    duplicate_path = next(path for path in source_paths if duplicate.id in path)
    assert "保留第一行\n保留第二行" in source[duplicate_path].decode()


@pytest.mark.asyncio
async def test_chapter_source_rejects_missing_or_duplicate_stable_ids_and_separates_same_title_volumes(
    session,
) -> None:
    project, volume, _root, nested = await _seed_chapters(session)
    second_volume = ProjectFolder(
        id="chapter-second-volume",
        project_id=project.id,
        scope="writing",
        title=volume.title,
        order=2,
    )
    second = Chapter(
        id="chapter-second-volume-chapter",
        project_id=project.id,
        volume_id=second_volume.id,
        title=nested.title,
        content="另一卷",
        order=1,
    )
    session.add_all([second_volume, second])
    await session.flush()

    files = read_zip(await export_markdown_source_bundle(session, project.id))
    paths = [path for path in files if path.startswith("正文/")]
    assert f"正文/第一卷--{volume.id}/第一章.md" in paths
    assert f"正文/第一卷--{second_volume.id}/第一章.md" in paths

    nested_path = next(
        path for path, value in files.items() if f"id: {nested.id}\n" in value.decode()
    )
    files["正文/复制.md"] = files[nested_path]
    with pytest.raises(BundleFormatError, match="duplicate target IDs"):
        parse_source_mapping(build_zip(files), project.id)

    files.pop("正文/复制.md")
    files[nested_path] = files[nested_path].replace(b"openfic_chapter:", b"other:", 1)
    with pytest.raises(BundleFormatError, match="chapter source metadata"):
        parse_source_mapping(build_zip(files), project.id)


@pytest.mark.asyncio
async def test_native_chapter_bundle_updates_volume_and_order_without_new_identity(session) -> None:
    project, _volume, _root, nested = await _seed_chapters(session)
    target_volume = ProjectFolder(
        id="chapter-target-volume",
        project_id=project.id,
        scope="writing",
        title="第二卷",
        order=2,
    )
    session.add(target_volume)
    await session.flush()
    files = read_zip(await export_project_bundle(session, project.id))
    manifest = yaml.safe_load(files["openfic.yaml"])
    item = next(entry for entry in manifest["documents"] if entry["id"] == nested.id)
    document = parse_markdown_document(files[item["path"]].decode())
    document.frontmatter["volume_id"] = target_volume.id
    document.frontmatter["order"] = 9
    files[item["path"]] = render_markdown_document(
        document.frontmatter, document.title, document.body
    )

    await apply_project_bundle(session, project.id, build_zip(files), "merge")

    assert nested.id == (await session.get(Chapter, nested.id)).id
    updated = await session.get(Chapter, nested.id)
    assert updated is not None
    assert updated.volume_id == target_volume.id
    assert updated.order == 9
