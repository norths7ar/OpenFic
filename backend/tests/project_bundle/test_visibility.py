import pytest

from app.core.agent_visibility import AGENT_VISIBILITY_STATES, AgentVisibility
from app.project_bundle import source_export, source_mapping
from app.project_bundle.archive import BundleFormatError, build_zip, read_zip
from app.project_bundle.export import export_project_bundle
from app.project_bundle.importer import parse_project_bundle
from app.project_bundle.markdown import parse_markdown_document, render_markdown_document
from app.storage.models.character import Character
from app.storage.models.note import Note
from app.storage.models.project import Project
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry


@pytest.mark.parametrize("state", AGENT_VISIBILITY_STATES, ids=lambda state: state.value)
async def test_all_material_visibility_round_trips_native_and_source(session, client, state):
    project = Project(id="visibility-roundtrip", title="可见范围")
    world = WorldInfo(id="visibility-world", project_id=project.id, name="设定")
    documents = [
        WorldInfoEntry(
            id="visibility-entry",
            world_info_id=world.id,
            uid=1,
            order=0,
            name="背景",
            content="背景内容",
            agent_visibility=state.value,
        ),
        Character(
            id="visibility-character",
            project_id=project.id,
            order=0,
            name="人物",
            description="人物内容",
            agent_visibility=state.value,
            is_favorited=True,
        ),
        Note(
            id="visibility-note",
            project_id=project.id,
            order=0,
            title="笔记",
            content="笔记内容",
            agent_visibility=state.value,
            is_locked=True,
        ),
        Note(
            id="visibility-outline",
            project_id=project.id,
            order=0,
            title="提纲",
            content="提纲内容",
            document_type="outline",
            agent_visibility=state.value,
            is_locked=True,
        ),
    ]
    session.add_all([project, world, *documents])
    await session.flush()
    native = parse_project_bundle(await export_project_bundle(session, project.id), project.id)
    assert len(native.documents) == 4
    assert {doc.semantic_fields["agent_visibility"] for doc in native.documents} == {state.value}
    assert all(
        "writing_visible" not in doc.semantic_fields and "is_hidden" not in doc.semantic_fields
        for doc in native.documents
    )
    source = await source_export.export_markdown_source_bundle(session, project.id)
    mapped = source_mapping.parse_source_mapping(source, project.id)
    assert {doc.target for doc in mapped} == {"worldbook", "characters", "notes", "outlines"}
    assert {doc.agent_visibility for doc in mapped} == {state.value}
    assert {doc.target_id for doc in mapped} == {doc.id for doc in documents}
    response = await client.post(
        f"/api/v1/projects/{project.id}/bundle/source/preview",
        files={"file": ("source.zip", source, "application/zip"), "mode": (None, "merge")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["summary"]["conflict"] == 0
    assert response.json()["summary"]["unchanged"] == 4


@pytest.mark.parametrize("value", ["invalid", "", True, None, []])
async def test_native_bundle_rejects_invalid_visibility(session, value):
    project = Project(id="invalid-visibility", title="测试")
    session.add_all(
        [
            project,
            Note(id="invalid-note", project_id=project.id, order=0, title="笔记", content="内容"),
        ]
    )
    await session.flush()
    files = read_zip(await export_project_bundle(session, project.id))
    path = next(path for path in files if path.endswith(".md"))
    doc = parse_markdown_document(files[path].decode())
    files[path] = render_markdown_document(
        {**doc.frontmatter, "agent_visibility": value}, doc.title, doc.body
    )
    with pytest.raises(BundleFormatError, match="agent_visibility"):
        parse_project_bundle(build_zip(files), project.id)


def test_visibility_catalog_covers_enum_exactly():
    assert [state.value for state in AGENT_VISIBILITY_STATES] == list(AgentVisibility)
    assert all(isinstance(state.value, AgentVisibility) for state in AGENT_VISIBILITY_STATES)


@pytest.mark.parametrize("state", AGENT_VISIBILITY_STATES, ids=lambda state: state.value)
def test_source_marker_round_trip_uses_enum_catalog(state):
    import yaml

    from app.project_bundle.item_markers import render_item

    bundle = build_zip(
        {
            "openfic-import.yaml": yaml.safe_dump(
                {
                    "schema": "openfic.import-map",
                    "version": 2,
                    "rules": [{"id": "notes", "target": "notes", "source": "笔记"}],
                }
            ),
            "笔记/a.md": render_item(
                {"id": "n", "title": "标题", "agent_visibility": state.value.value}, "内容"
            ),
        }
    )
    parsed = source_mapping.parse_source_mapping(bundle, "p")[0]
    assert parsed.title == "标题"
    assert parsed.agent_visibility is state.value


def test_nested_item_visibility_does_not_change_child_anchor():
    rule = {
        "id": "r",
        "target": "outlines",
        "source": "a.md",
        "split": {"type": "headings", "item_levels": [2, 3]},
    }
    public = source_mapping._mapped_items("a.md", "# 根\n## 父\n### 子\n内容", rule)
    hidden = source_mapping._mapped_items("a.md", "# 根\n## 父[隐藏]\n### 子[仅全局]\n内容", rule)
    assert [item.anchor for item in public] == [item.anchor for item in hidden]
    assert [item.agent_visibility for item in hidden] == ["none", "global"]
