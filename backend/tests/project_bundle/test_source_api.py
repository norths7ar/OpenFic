from uuid import uuid4

import pytest
import yaml
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.project_bundle.archive import build_zip
from app.storage.models.character import Character
from app.storage.models.note import Note
from app.storage.models.project import Project


def _source_bundle(
    project_id: str,
    *,
    volume_body: str = "卷内容",
    character_body: str = "角色内容",
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
                "agent_visibility": "global",
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
                "split": {"type": "headings", "item_levels": [2, 3]},
                "category_path": ["提纲"],
                "category_levels": [2],
            },
        ],
    }
    return build_zip(
        {
            "openfic-import.yaml": yaml.safe_dump(config, allow_unicode=True, sort_keys=True),
            "world.md": "# 世界\n## 体系\n### 灵气\n灵气内容",
            "character.md": f"# 主角\n\n{character_body}",
            "outline.md": (
                "# 总纲\n## 第一阶段\n阶段序言\n### 第一卷\n"
                f"{volume_body}\n## 第二阶段\n第二阶段内容"
            ),
        }
    )


async def _create_project(session, project_id: str | None = None) -> Project:
    project_id = project_id or f"source-api-{uuid4().hex}"
    project = Project(id=project_id, title="源导入 API 测试")
    session.add(project)
    await session.flush()
    return project


def _upload(data: bytes, mode: str = "merge") -> dict:
    return {
        "file": ("source.openfic.zip", data, "application/zip"),
        "mode": (None, mode),
    }


@pytest.mark.asyncio
async def test_source_apply_updates_changed_source(client: AsyncClient, session) -> None:
    project = await _create_project(session)
    first = _source_bundle(project.id)
    assert (
        await client.post(
            f"/api/v1/projects/{project.id}/bundle/source/apply",
            files=_upload(first),
        )
    ).status_code == 200

    changed = await client.post(
        f"/api/v1/projects/{project.id}/bundle/source/apply",
        files=_upload(
            _source_bundle(project.id, volume_body="卷内容 v2", character_body="角色内容 v2")
        ),
    )
    assert changed.status_code == 200
    assert changed.json()["summary"] == {
        "create": 0,
        "update": 2,
        "unchanged": 6,
        "conflict": 0,
    }
    notes = (
        await session.execute(
            Note.__table__.select().where(
                (Note.project_id == project.id) & (Note.content == "卷内容 v2")
            )
        )
    ).all()
    assert len(notes) == 1


@pytest.mark.asyncio
async def test_source_apply_conflict_does_not_partially_write(
    client: AsyncClient, session, db_engine
) -> None:
    project = await _create_project(session)
    project_id = project.id
    first = _source_bundle(project.id)
    assert (
        await client.post(
            f"/api/v1/projects/{project_id}/bundle/source/apply",
            files=_upload(first),
        )
    ).status_code == 200

    note_id = (
        await session.execute(
            select(Note.id).where((Note.project_id == project.id) & (Note.content == "卷内容"))
        )
    ).scalar_one_or_none()
    assert note_id is not None
    # Use an independent session to model a saved OpenFic edit from another
    # request/transaction; the import request must not roll it back.
    async with db_engine.connect() as edit_conn:
        edit_session = AsyncSession(bind=edit_conn, expire_on_commit=False)
        note_obj = await edit_session.get(Note, note_id)
        assert note_obj is not None
        note_obj.content = "OpenFic 本地改动"
        await edit_session.commit()
        await edit_session.close()

    conflict = await client.post(
        f"/api/v1/projects/{project_id}/bundle/source/apply",
        files=_upload(
            _source_bundle(project_id, volume_body="卷内容 v2", character_body="角色内容 v2")
        ),
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["conflicts"]

    current_note = (
        await session.execute(
            select(Note).where(
                (Note.project_id == project_id) & (Note.content == "OpenFic 本地改动")
            )
        )
    ).scalar_one_or_none()
    assert current_note is not None and current_note.content == "OpenFic 本地改动"
    characters = (
        await session.execute(
            Character.__table__.select().where(
                (Character.project_id == project_id) & (Character.description == "角色内容")
            )
        )
    ).all()
    assert len(characters) == 1
