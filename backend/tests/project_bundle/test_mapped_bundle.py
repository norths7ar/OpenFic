import pytest
import yaml
from sqlalchemy import select
from sqlmodel import col

from app.project_bundle.apply import apply_project_bundle
from app.project_bundle.archive import build_zip
from app.project_bundle.importer import parse_project_bundle, preview_project_bundle
from app.project_bundle.mapped_bundle import (
    build_mapped_project_bundle,
    persist_mapped_import_bindings,
)
from app.storage.models.note import Note
from app.storage.models.project import Project
from app.storage.models.project_import_binding import ProjectImportBinding
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry


def _source_bundle(
    project_id: str,
    *,
    volume_body: str = "卷内容",
    world_body: str = "### 灵气\n灵气内容",
) -> bytes:
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
                "writing_visible": False,
            },
            {
                "id": "character",
                "target": "characters",
                "source": "character.md",
                "split": {"type": "file"},
            },
            {
                "id": "outline",
                "target": "notes",
                "source": "outline.md",
                "split": {"type": "headings", "item_levels": [3]},
                "folder_level": 2,
            },
        ],
    }
    return build_zip(
        {
            "openfic-import.yaml": yaml.safe_dump(config, allow_unicode=True, sort_keys=True),
            "world.md": f"# 世界\n## 体系\n{world_body}",
            "character.md": "# 主角\n\n角色内容",
            "outline.md": (
                "# 总纲\n## 第一阶段\n阶段序言\n### 第一卷\n"
                f"{volume_body}\n## 第二阶段\n第二阶段内容"
            ),
        }
    )


@pytest.mark.asyncio
async def test_mapped_bundle_round_trip_and_three_way_baseline(session) -> None:
    project = Project(id="mapped-project", title="映射项目")
    session.add(project)
    await session.flush()

    source = _source_bundle(project.id)
    mapped = await build_mapped_project_bundle(session, project.id, source)
    parsed = parse_project_bundle(mapped.data, project.id)
    assert len(parsed.documents) == 3
    assert len(parsed.note_categories) == 1
    assert {document.kind for document in parsed.documents} == {
        "world_entry",
        "character",
        "note",
    }
    assert all(spec.incoming_hash.startswith("sha256:") for spec in mapped.bindings)

    preview = await preview_project_bundle(session, project.id, mapped.data, "merge")
    assert preview.summary == {
        "create": 5,
        "update": 0,
        "unchanged": 0,
        "conflict": 0,
    }
    await apply_project_bundle(session, project.id, mapped.data, "merge")
    await persist_mapped_import_bindings(session, project.id, mapped.bindings)

    rebuilt = await build_mapped_project_bundle(session, project.id, source)
    unchanged = await preview_project_bundle(session, project.id, rebuilt.data, "merge")
    assert unchanged.summary == {
        "create": 0,
        "update": 0,
        "unchanged": 5,
        "conflict": 0,
    }
    changed_source = _source_bundle(project.id, volume_body="卷内容 v2")
    changed = await build_mapped_project_bundle(session, project.id, changed_source)
    changed_preview = await preview_project_bundle(session, project.id, changed.data, "merge")
    assert changed_preview.summary["update"] == 1
    await apply_project_bundle(session, project.id, changed.data, "merge")
    await persist_mapped_import_bindings(session, project.id, changed.bindings)
    changed_note_spec = next(
        spec
        for spec in changed.bindings
        if spec.target_kind == "note" and "H3:第一卷" in spec.source_anchor
    )
    changed_note = await session.get(Note, changed_note_spec.target_id)
    assert changed_note is not None and changed_note.content == "卷内容 v2"

    changed_note.content = "OpenFic 内编辑"
    await session.flush()
    third_source = _source_bundle(project.id, volume_body="卷内容 v3")
    third = await build_mapped_project_bundle(session, project.id, third_source)
    conflict = await preview_project_bundle(session, project.id, third.data, "merge")
    assert conflict.summary["conflict"] == 1
    assert next(item for item in conflict.items if item.action == "conflict").reason == (
        "current_changed"
    )

    bindings = list(
        (
            await session.execute(
                select(ProjectImportBinding).where(
                    col(ProjectImportBinding.project_id) == project.id
                )
            )
        ).scalars()
    )
    assert len(bindings) == 5


@pytest.mark.asyncio
async def test_mapped_ids_are_isolated_between_projects(session) -> None:
    first = Project(id="mapped-first", title="一")
    second = Project(id="mapped-second", title="二")
    session.add_all([first, second])
    await session.flush()

    first_bundle = await build_mapped_project_bundle(session, first.id, _source_bundle(first.id))
    second_bundle = await build_mapped_project_bundle(session, second.id, _source_bundle(second.id))
    first_targets = {(spec.target_kind, spec.target_id) for spec in first_bundle.bindings}
    second_targets = {(spec.target_kind, spec.target_id) for spec in second_bundle.bindings}
    assert first_targets.isdisjoint(second_targets)


@pytest.mark.asyncio
async def test_mapped_world_uids_follow_existing_book_and_remain_stable(
    session,
) -> None:
    project = Project(id="mapped-world-uids", title="世界书 UID")
    world = WorldInfo(id="existing-world", project_id=project.id, name="世界")
    existing = WorldInfoEntry(
        id="existing-entry",
        world_info_id=world.id,
        uid=1,
        name="已有条目",
        content="内容",
        order=0,
    )
    session.add_all([project, world, existing])
    await session.flush()

    first = await build_mapped_project_bundle(session, project.id, _source_bundle(project.id))
    parsed_first = parse_project_bundle(first.data, project.id)
    first_entry = next(
        document for document in parsed_first.documents if document.kind == "world_entry"
    )
    assert first_entry.semantic_fields["uid"] == 2
    await apply_project_bundle(session, project.id, first.data, "merge")
    await persist_mapped_import_bindings(session, project.id, first.bindings)

    second = await build_mapped_project_bundle(
        session,
        project.id,
        _source_bundle(
            project.id,
            world_body="### 新条目\n新内容\n### 灵气\n灵气内容",
        ),
    )
    parsed_second = parse_project_bundle(second.data, project.id)
    by_title = {
        document.title: document.semantic_fields["uid"]
        for document in parsed_second.documents
        if document.kind == "world_entry"
    }
    assert by_title == {"新条目": 3, "灵气": 2}
