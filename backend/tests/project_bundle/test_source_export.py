from uuid import uuid4

import yaml
from httpx import AsyncClient

from app.project_bundle.archive import build_zip, read_zip
from app.storage.models.note import Note
from app.storage.models.project import Project
from app.storage.models.project_folder import ProjectFolder as NoteCategory


async def _create_project(session) -> Project:
    project = Project(id=f"source-export-{uuid4().hex}", title="源导出测试")
    session.add(project)
    await session.flush()
    return project


async def test_source_round_trip_preserves_same_named_folder_ids(client, session):
    project = await _create_project(session)
    for index in range(2):
        folder = NoteCategory(
            id=f"same-folder-{index}",
            project_id=project.id,
            scope="note",
            title="同名",
            order=index,
        )
        note = Note(
            id=f"same-folder-note-{index}",
            project_id=project.id,
            category_id=folder.id,
            title=f"条目{index}",
            content=f"内容{index}",
            order=index,
        )
        session.add_all([folder, note])
    await session.flush()
    exported = await client.get(f"/api/v1/projects/{project.id}/bundle/source/export")
    assert exported.status_code == 200
    preview = await client.post(
        f"/api/v1/projects/{project.id}/bundle/source/preview", files=_upload(exported.content)
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["summary"]["conflict"] == 0
    config = yaml.safe_load(read_zip(exported.content)["openfic-import.yaml"])
    assert {rule["folder_target_id"] for rule in config["rules"] if "folder_target_id" in rule} == {
        "same-folder-0",
        "same-folder-1",
    }


def _source_bundle(project_id: str) -> bytes:
    config = {
        "schema": "openfic.import-map",
        "version": 1,
        "project_id": project_id,
        "rules": [
            {
                "id": "world",
                "target": "worldbook",
                "source": "world.md",
                "split": {"type": "headings", "item_levels": [3]},
                "section_level": 2,
            },
            {
                "id": "character",
                "target": "characters",
                "source": "character.md",
                "split": {"type": "file"},
            },
            {
                "id": "outline",
                "target": "outlines",
                "source": "outline.md",
                "split": {"type": "headings", "item_levels": [3]},
                "category_levels": [2],
            },
        ],
    }
    return build_zip(
        {
            "openfic-import.yaml": yaml.safe_dump(config, allow_unicode=True),
            "world.md": "# 世界\n## 体系\n### 灵气\n灵气内容",
            "character.md": "# 主角\n\n角色内容",
            "outline.md": "# 总纲\n## 第一阶段\n### 第一卷\n卷内容",
        }
    )


def _upload(data: bytes) -> dict:
    return {"file": ("source.zip", data, "application/zip"), "mode": (None, "merge")}


async def test_source_export_uses_saved_mapping_and_falls_back_by_semantic_type(
    client: AsyncClient, session
) -> None:
    project = await _create_project(session)
    source = _source_bundle(project.id)
    applied = await client.post(
        f"/api/v1/projects/{project.id}/bundle/source/apply",
        files=_upload(source),
    )
    assert applied.status_code == 200

    category = NoteCategory(
        id="new-outline-category",
        project_id=project.id,
        title="新增提纲",
        scope="outline",
        order=0,
    )
    note = Note(
        id="new-outline",
        project_id=project.id,
        category_id=category.id,
        title="额外一幕",
        content="OpenFic 中新写的提纲",
        document_type="outline",
        order=0,
    )
    session.add_all([category, note])
    await session.flush()

    response = await client.get(f"/api/v1/projects/{project.id}/bundle/source/export")
    assert response.status_code == 200
    files = read_zip(response.content)
    assert {"world.md", "character.md", "outline.md"}.issubset(files)
    assert "### 第一卷" in files["outline.md"].decode()
    fallback_path = next(path for path in files if path.startswith("提纲/新增提纲/"))
    assert "OpenFic 中新写的提纲" in files[fallback_path].decode()

    config = yaml.safe_load(files["openfic-import.yaml"])
    fallback_rule = next(
        rule for rule in config["rules"] if rule["id"] == "openfic-note-new-outline"
    )
    assert fallback_rule["target"] == "outlines"
    assert fallback_rule["folder_path"] == ["新增提纲"]

    preview = await client.post(
        f"/api/v1/projects/{project.id}/bundle/source/preview",
        files=_upload(response.content),
    )
    assert preview.status_code == 200
    assert preview.json()["summary"]["conflict"] == 0, preview.json()


async def test_source_export_without_profile_generates_portable_optional_map(
    client: AsyncClient, session
) -> None:
    project = await _create_project(session)

    response = await client.get(f"/api/v1/projects/{project.id}/bundle/source/export")

    assert response.status_code == 200
    files = read_zip(response.content)
    assert set(files) == {"openfic-import.yaml"}
    config = yaml.safe_load(files["openfic-import.yaml"])
    assert "project_id" not in config
    assert all(rule["required"] is False for rule in config["rules"])
