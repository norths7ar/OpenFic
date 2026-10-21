import yaml
from sqlalchemy import select

from app.project_bundle.archive import build_zip, read_zip
from app.project_bundle.export import export_project_bundle
from app.project_bundle.importer import parse_project_bundle, preview_project_bundle
from app.project_bundle.mapped_bundle import build_mapped_project_bundle
from app.project_bundle.source_export import export_markdown_source_bundle
from app.storage.models.project import Project
from app.storage.models.project_folder import ProjectFolder
from app.storage.models.world_info_entry import WorldInfoEntry


def _bundle(config, text="# 根\n## 条目\n正文"):
    return build_zip(
        {"openfic-import.yaml": yaml.safe_dump(config, allow_unicode=True), "a.md": text}
    )


async def test_grouped_source_preserves_arbitrary_order_section_and_folder_metadata(
    client, session
):
    project = Project(id="grouped-metadata", title="分组源")
    session.add(project)
    await session.flush()
    config = {
        "schema": "openfic.import-map",
        "version": 1,
        "rules": [
            {
                "id": "world",
                "target": "worldbook",
                "source": "a.md",
                "split": {"type": "headings", "item_levels": [3]},
                "section_level": 2,
            }
        ],
    }
    data = _bundle(config, "# 根\n## 原分区\n### 第一条\n正文\n### 第二条\n正文")
    result = await client.post(
        f"/api/v1/projects/{project.id}/bundle/source/apply",
        files={"file": ("source.zip", data, "application/zip")},
    )
    assert result.status_code == 200, result.text
    entries = list((await session.execute(select(WorldInfoEntry))).scalars())
    for index, entry in enumerate(entries):
        entry.order = [17, 42][index]
        entry.section = "独立保留的分区字段"
        entry.content = f"正文{index}\r\n末段\r\n"
        entry.agent_visibility = "none"
    folder = (await session.execute(select(ProjectFolder))).scalar_one()
    folder.description = "保留文件夹说明"
    # Same-name empty folders must retain distinct identities too.
    session.add(
        ProjectFolder(
            id="empty-same-name",
            project_id=project.id,
            scope="world",
            title=folder.title,
            description="空文件夹",
            order=99,
        )
    )
    await session.flush()
    before = parse_project_bundle(await export_project_bundle(session, project.id), project.id)
    source = await export_markdown_source_bundle(session, project.id)
    exported_config = yaml.safe_load(read_zip(source)["openfic-import.yaml"])
    assert len(exported_config["folders"]) == 2
    mapped = await build_mapped_project_bundle(session, project.id, source)
    after = parse_project_bundle(mapped.data, project.id)

    def key(doc):
        return doc.kind, doc.id, doc.title, doc.body, doc.semantic_fields

    assert sorted(map(key, before.documents)) == sorted(map(key, after.documents))
    assert [folder.semantic_fields for folder in before.project_folders] == [
        folder.semantic_fields for folder in after.project_folders
    ]
    preview = await preview_project_bundle(session, project.id, mapped.data, "merge")
    assert preview.summary == {"create": 0, "update": 0, "unchanged": 4, "conflict": 0}
