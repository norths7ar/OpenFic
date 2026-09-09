import pytest
import yaml

from app.project_bundle.archive import BundleFormatError, build_zip, read_zip
from app.project_bundle.item_markers import parse_items, render_item
from app.project_bundle.source_export import export_markdown_source_bundle
from app.project_bundle.source_mapping import parse_source_mapping
from app.storage.models.character import Character
from app.storage.models.note import Note
from app.storage.models.project import Project
from app.storage.models.project_folder import ProjectFolder
from app.storage.models.project_import_profile import ProjectImportProfile


def config():
    return {
        "schema": "openfic.import-map",
        "version": 2,
        "rules": [{"id": "notes", "target": "notes", "source": "创作/随记", "layout": "merged"}],
    }


def bundle(files, settings=None):
    return build_zip(
        {"openfic-import.yaml": yaml.safe_dump(settings or config(), allow_unicode=True), **files}
    )


@pytest.mark.parametrize(
    "body",
    [
        "# First\n# Second\n###### Skipped levels",
        "\r\nText\r\n\r\n",
        "\n",
        "",
        "first\rlast\n",
        "```md\n<!-- openfic:item\nid: example\n-->\n```",
        "<!-- openfic:item\n\\<!-- openfic:item\n\\\\<!-- openfic:item",
        "```unfinished\n# Text",
    ],
)
def test_markers_preserve_exact_body_and_cannot_collide(body):
    first = render_item({"id": "one", "title": "Name --> suffix"}, body)
    second = render_item({"id": "two", "title": "Other"}, "second")
    parsed = parse_items(first + second)
    assert [(meta["id"], content) for meta, content in parsed] == [("one", body), ("two", "second")]
    assert parsed[0][0]["title"] == "Name --> suffix"


def test_directory_owns_folder_for_split_and_merged_files():
    one = render_item({"id": "one", "title": "A"}, "# Any heading")
    two = render_item({"id": "two", "title": "B"}, "## More")
    split = parse_source_mapping(
        bundle({"创作/随记/草稿/a.md": one, "创作/随记/草稿/b.md": two}), "p"
    )
    merged = parse_source_mapping(bundle({"创作/随记/草稿/all.md": one + two}), "p")
    assert [(item.target_id, item.body, item.category_path) for item in split] == [
        (item.target_id, item.body, item.category_path) for item in merged
    ]
    moved = parse_source_mapping(bundle({"创作/随记/完成/all.md": one + two}), "p")
    assert moved[0].target_id == "one"
    assert moved[0].category_path == ["完成"]


def test_rejects_nested_folders_overlapping_roots_and_marker_folder_override():
    item = render_item({"id": "one", "title": "A"}, "content")
    with pytest.raises(BundleFormatError, match="one folder level"):
        parse_source_mapping(bundle({"创作/随记/a/b/file.md": item}), "p")
    settings = config()
    settings["rules"].append({"id": "other", "target": "characters", "source": "创作"})
    with pytest.raises(BundleFormatError, match="overlap"):
        parse_source_mapping(bundle({}, settings), "p")
    with pytest.raises(BundleFormatError, match="fields"):
        parse_items(render_item({"id": "one", "title": "A", "folder": "Override"}, ""))


async def test_v2_export_honors_custom_root_and_merges_only_within_folder(session):
    project = Project(id="directory-export", title="Directory")
    folder = ProjectFolder(id="folder", project_id=project.id, scope="note", title="草稿", order=1)
    session.add_all(
        [
            project,
            folder,
            ProjectImportProfile(project_id=project.id, mapping_yaml=yaml.safe_dump(config())),
            Note(id="one", project_id=project.id, title="One", content="# H1\n# H1", order=0),
            Note(id="two", project_id=project.id, title="Two", content="Text", order=1),
            Note(
                id="three",
                project_id=project.id,
                title="Three",
                category_id=folder.id,
                content="Draft",
                order=2,
            ),
        ]
    )
    await session.flush()
    exported = await export_markdown_source_bundle(session, project.id)
    files = read_zip(exported)
    assert {path for path in files if path.endswith(".md")} == {
        "创作/随记/条目.md",
        "创作/随记/草稿/条目.md",
    }
    items = {item.target_id: item for item in parse_source_mapping(exported, project.id)}
    assert items["one"].body == "# H1\n# H1"
    assert items["three"].category_target_ids == [folder.id]


async def test_file_move_retains_baseline_and_refreshes_binding(client, session):
    project = Project(id="directory-move", title="Move")
    session.add(project)
    await session.flush()
    prefix = f"/api/v1/projects/{project.id}/bundle/source"

    def upload(data):
        return {"file": ("source.zip", data, "application/zip"), "mode": (None, "merge")}

    original = bundle(
        {
            "创作/随记/old.md": render_item(
                {"id": "moving", "title": "Original", "order": 0}, "baseline"
            )
        }
    )
    applied = await client.post(prefix + "/apply", files=upload(original))
    assert applied.status_code == 200, applied.text
    moved = bundle(
        {
            "创作/随记/新目录/renamed.md": render_item(
                {"id": "moving", "title": "Renamed", "order": 0}, "external"
            )
        }
    )
    preview = await client.post(prefix + "/preview", files=upload(moved))
    assert preview.status_code == 200, preview.text
    assert preview.json()["summary"]["conflict"] == 0
    applied = await client.post(prefix + "/apply", files=upload(moved))
    assert applied.status_code == 200, applied.text
    note = await session.get(Note, "moving")
    await session.refresh(note)
    note.content = "local change"
    await session.flush()
    another_move = bundle(
        {
            "创作/随记/elsewhere.md": render_item(
                {"id": "moving", "title": "Renamed", "order": 0}, "another external change"
            )
        }
    )
    preview = await client.post(prefix + "/preview", files=upload(another_move))
    assert preview.status_code == 200, preview.text
    assert preview.json()["summary"]["conflict"] == 1


@pytest.mark.parametrize("has_character", [False, True])
@pytest.mark.parametrize("custom_root", ["角色", "角色/资料"])
async def test_default_export_rules_do_not_collide_with_user_roots_or_ids(
    session, has_character, custom_root
):
    project = Project(id="custom-root", title="Custom")
    custom_rule = {"id": "openfic-characters", "target": "worldbook", "source": custom_root}
    session.add_all(
        [
            project,
            ProjectImportProfile(
                project_id=project.id,
                mapping_yaml=yaml.safe_dump(
                    {
                        "schema": "openfic.import-map",
                        "version": 2,
                        "rules": [custom_rule],
                    }
                ),
            ),
        ]
    )
    if has_character:
        session.add(Character(id="hero", project_id=project.id, name="Hero", order=0))
    await session.flush()
    exported = await export_markdown_source_bundle(session, project.id)
    settings = yaml.safe_load(read_zip(exported)["openfic-import.yaml"])
    assert settings["rules"][0] == custom_rule
    character_rule = next(rule for rule in settings["rules"] if rule["target"] == "characters")
    assert character_rule["source"] == "角色-2"
    assert character_rule["id"] == "openfic-characters-2"
    items = parse_source_mapping(exported, project.id)
    assert [item.target_id for item in items] == (["hero"] if has_character else [])
