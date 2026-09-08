import pytest
import yaml
from sqlalchemy import select

from app.project_bundle.archive import BundleFormatError, build_zip, read_zip
from app.project_bundle.export import export_project_bundle
from app.project_bundle.importer import parse_project_bundle, preview_project_bundle
from app.project_bundle.mapped_bundle import build_mapped_project_bundle
from app.project_bundle.markdown import parse_markdown_document, render_markdown_document
from app.project_bundle.source_export import export_markdown_source_bundle
from app.project_bundle.source_mapping import parse_source_mapping
from app.storage.models.project import Project
from app.storage.models.project_folder import ProjectFolder
from app.storage.models.world_info_entry import WorldInfoEntry


def _bundle(config, text="# 根\n## 条目\n正文"):
    return build_zip(
        {"openfic-import.yaml": yaml.safe_dump(config, allow_unicode=True), "a.md": text}
    )


def _config():
    return {
        "schema": "openfic.import-map",
        "version": 1,
        "rules": [
            {
                "id": "r",
                "target": "notes",
                "source": "a.md",
                "split": {"type": "headings", "item_levels": [2]},
            }
        ],
        "items": [
            {
                "rule_id": "r",
                "source": "a.md",
                "anchor": "H1:根/H2:条目",
                "target_id": "item",
                "order": 47,
            }
        ],
    }


@pytest.mark.parametrize(
    "body",
    [
        "\n正文\n\n",
        "正文\r\n末段\r\n",
        "正文\r末段\r",
        "正文\r\n中段\n末段\r",
        "\r\n\n",
        "正文  \n",
        "",
    ],
)
def test_native_markdown_preserves_exact_body_line_endings(body):
    assert parse_markdown_document(render_markdown_document({}, "标题", body)).body == body


def test_metadata_rejects_heading_rename_until_anchor_is_updated():
    config = _config()
    with pytest.raises(BundleFormatError, match="unmatched anchors"):
        parse_source_mapping(_bundle(config, "# 根\n## 改名\n正文"), "p")
    config["items"][0]["anchor"] = "H1:根/H2:改名"
    item = parse_source_mapping(_bundle(config, "# 根\n## 改名\n修改正文"), "p")[0]
    assert (item.title, item.target_id, item.order, item.body) == ("改名", "item", 47, "修改正文")


def test_metadata_allows_new_items_without_matching_metadata():
    parsed = parse_source_mapping(_bundle(_config(), "# 根\n## 条目\n正文\n## 新条目\n新正文"), "p")
    assert [(item.title, item.target_id) for item in parsed] == [("条目", "item"), ("新条目", None)]


@pytest.mark.parametrize(
    "change",
    [
        {"folder_id": []},
        {"target_id": []},
        {"order": True},
        {"is_locked": "true"},
        {"body_format": {"prefix": "", "suffix": "", "line_ending": []}},
        {"body_format": {"prefix": "", "suffix": "", "line_endings": [[]]}},
        {"is_favorited": True},
        {"section": "wrong type"},
    ],
)
def test_invalid_item_metadata_is_a_bundle_error(change):
    config = _config()
    config["items"][0].update(change)
    with pytest.raises(BundleFormatError):
        parse_source_mapping(_bundle(config), "p")


def test_duplicate_metadata_and_target_ids_are_rejected():
    config = _config()
    config["items"].append(dict(config["items"][0]))
    with pytest.raises(BundleFormatError, match="duplicate"):
        parse_source_mapping(_bundle(config), "p")
    config["items"][1]["anchor"] = "H1:根/H2:另条目"
    with pytest.raises(BundleFormatError, match="duplicate target IDs"):
        parse_source_mapping(_bundle(config, "# 根\n## 条目\n正文\n## 另条目\n正文"), "p")


@pytest.mark.parametrize("scope", [[], "character"])
def test_invalid_or_wrong_folder_scope_is_rejected(scope):
    config = _config()
    config["folders"] = [{"id": "f", "scope": scope, "title": "文件夹", "order": 0}]
    config["items"][0]["folder_id"] = "f"
    with pytest.raises(BundleFormatError):
        parse_source_mapping(_bundle(config), "p")


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
