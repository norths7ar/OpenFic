
import pytest

from app.project_bundle.archive import read_zip
from app.project_bundle.export import export_project_bundle
from app.project_bundle.source_export import export_markdown_source_bundle
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
    assert any("序章--" in path for path in source_paths)
    duplicate_path = next(path for path in source_paths if duplicate.id in path)
    assert "保留第一行\n保留第二行" in source[duplicate_path].decode()
