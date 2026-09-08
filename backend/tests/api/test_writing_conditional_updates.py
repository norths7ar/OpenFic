from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models.chapter import Chapter
from app.storage.models.note import Note


async def _project(client: AsyncClient) -> tuple[str, str]:
    response = await client.post("/api/v1/projects", data={"title": "条件保存"})
    assert response.status_code == 201
    project_id = response.json()["id"]
    volumes = (await client.get(f"/api/v1/projects/{project_id}/volumes")).json()
    return project_id, volumes[0]["id"]


async def _chapter(client: AsyncClient, project_id: str, volume_id: str) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/chapters",
        json={"volume_id": volume_id, "title": "base title", "content": "base content"},
    )
    assert response.status_code == 201
    return response.json()


async def _note(client: AsyncClient, project_id: str) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/notes",
        json={"title": "base title", "content": "base content"},
    )
    assert response.status_code == 201
    return response.json()


def _base(item: dict) -> dict:
    return {
        "base_updated_at": item["updated_at"],
        "base_title": item["title"],
        "base_content": item["content"],
    }


@pytest.mark.asyncio
async def test_chapter_conditional_update_paths(client: AsyncClient, session: AsyncSession) -> None:
    project_id, volume_id = await _project(client)
    item = await _chapter(client, project_id, volume_id)
    success = await client.patch(
        f"/api/v1/chapters/{item['id']}", json={**_base(item), "content": "local"}
    )
    assert success.status_code == 200 and success.json()["content"] == "local"

    item = await _chapter(client, project_id, volume_id)
    await session.execute(
        update(Chapter)
        .where(Chapter.id == item["id"])
        .values(updated_at=datetime.now(UTC) + timedelta(seconds=1))
    )
    metadata = await client.patch(
        f"/api/v1/chapters/{item['id']}", json={**_base(item), "content": "local"}
    )
    assert metadata.status_code == 200 and metadata.json()["content"] == "local"

    item = await _chapter(client, project_id, volume_id)
    await session.execute(update(Chapter).where(Chapter.id == item["id"]).values(content="remote"))
    conflict = await client.patch(
        f"/api/v1/chapters/{item['id']}", json={**_base(item), "content": "local"}
    )
    assert conflict.status_code == 409
    assert (await client.get(f"/api/v1/chapters/{item['id']}")).json()["content"] == "remote"

    item = await _chapter(client, project_id, volume_id)
    timestamp_only = await client.patch(
        f"/api/v1/chapters/{item['id']}",
        json={"base_updated_at": item["updated_at"], "content": "timestamp only"},
    )
    assert (
        timestamp_only.status_code == 200 and timestamp_only.json()["content"] == "timestamp only"
    )

    item = await _chapter(client, project_id, volume_id)
    legacy = await client.patch(f"/api/v1/chapters/{item['id']}", json={"content": "legacy"})
    assert legacy.status_code == 200 and legacy.json()["content"] == "legacy"


@pytest.mark.asyncio
async def test_note_conditional_update_paths(client: AsyncClient, session: AsyncSession) -> None:
    project_id, _ = await _project(client)
    item = await _note(client, project_id)
    success = await client.patch(
        f"/api/v1/notes/{item['id']}", json={**_base(item), "content": "local"}
    )
    assert success.status_code == 200 and success.json()["content"] == "local"

    item = await _note(client, project_id)
    await session.execute(
        update(Note)
        .where(Note.id == item["id"])
        .values(updated_at=datetime.now(UTC) + timedelta(seconds=1))
    )
    metadata = await client.patch(
        f"/api/v1/notes/{item['id']}", json={**_base(item), "content": "local"}
    )
    assert metadata.status_code == 200 and metadata.json()["content"] == "local"

    item = await _note(client, project_id)
    await session.execute(update(Note).where(Note.id == item["id"]).values(content="remote"))
    conflict = await client.patch(
        f"/api/v1/notes/{item['id']}", json={**_base(item), "content": "local"}
    )
    assert conflict.status_code == 409
    assert (await client.get(f"/api/v1/notes/{item['id']}")).json()["content"] == "remote"

    item = await _note(client, project_id)
    timestamp_only = await client.patch(
        f"/api/v1/notes/{item['id']}",
        json={"base_updated_at": item["updated_at"], "content": "timestamp only"},
    )
    assert (
        timestamp_only.status_code == 200 and timestamp_only.json()["content"] == "timestamp only"
    )

    item = await _note(client, project_id)
    legacy = await client.patch(f"/api/v1/notes/{item['id']}", json={"content": "legacy"})
    assert legacy.status_code == 200 and legacy.json()["content"] == "legacy"
