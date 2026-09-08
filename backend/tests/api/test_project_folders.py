"""Shared project-folder behavior."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_writing_folder_delete_keeps_root_chapters(client: AsyncClient, session) -> None:
    project = (await client.post("/api/v1/projects", data={"title": "项目"})).json()
    project_id = project["id"]
    folder = (
        await client.get(f"/api/v1/projects/{project_id}/folders", params={"scope": "writing"})
    ).json()["items"][0]
    chapter = await client.post(
        f"/api/v1/projects/{project_id}/chapters",
        json={"volume_id": folder["id"], "title": "章节", "content": "正文"},
    )
    assert chapter.status_code == 201, chapter.text
    assert (await client.delete(f"/api/v1/folders/{folder['id']}")).status_code == 204
    listing = await client.get(f"/api/v1/projects/{project_id}/chapters")
    assert listing.status_code == 200, listing.text
    assert listing.json()["volumes"] == []
    assert listing.json()["root_chapters"][0]["id"] == chapter.json()["id"]
    assert listing.json()["root_chapters"][0]["volume_id"] is None
    from app.chapter_export.service import create_export_plan
    from app.storage.services import chapter_service

    searched = await chapter_service.search_chapters(session, project_id, "正文")
    assert [result.chapter_id for result in searched.results] == [chapter.json()["id"]]
    assert searched.results[0].volume_title == "根目录"
    candidates = await chapter_service.search_mention_candidates(session, project_id, "章节")
    assert chapter.json()["id"] in {item.id for item in candidates}
    export = await create_export_plan(
        session,
        project_id=project_id,
        selected_volume_ids=[],
        included_chapter_ids=[chapter.json()["id"]],
        excluded_chapter_ids=[],
        local_date="2026-09-07",
    )
    assert export.chapter_ids == [chapter.json()["id"]]
    assert export.chapters[0].volume_id is None

    root = await client.post(
        f"/api/v1/projects/{project_id}/chapters",
        json={"volume_id": None, "title": "根章节", "content": "正文"},
    )
    assert root.status_code == 201, root.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope", ["writing", "discussion", "world", "character", "outline", "note"]
)
async def test_folder_identity_and_description(client: AsyncClient, scope: str) -> None:
    project = (await client.post("/api/v1/projects", data={"title": "项目"})).json()
    url = f"/api/v1/projects/{project['id']}/folders"
    first = await client.post(url, json={"scope": scope, "title": "同名", "description": "说明"})
    second = await client.post(url, json={"scope": scope, "title": "同名"})
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["title"] == second.json()["title"] == "同名"
    assert first.json()["description"] == "说明"
    edited = await client.patch(f"/api/v1/folders/{first.json()['id']}", json={"description": None})
    assert edited.status_code == 200
    assert edited.json()["description"] is None
    assert edited.json()["title"] == "同名"


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["outline", "note"])
async def test_document_folder_preserves_content_and_visibility(
    client: AsyncClient, scope: str
) -> None:
    project = (await client.post("/api/v1/projects", data={"title": "项目"})).json()
    project_id = project["id"]
    folder = (
        await client.post(
            f"/api/v1/projects/{project_id}/folders", json={"scope": scope, "title": "分组"}
        )
    ).json()
    response = await client.post(
        f"/api/v1/projects/{project_id}/notes",
        json={
            "document_type": scope,
            "title": "条目",
            "content": "正文",
            "category_id": folder["id"],
        },
    )
    assert response.status_code == 201, response.text
    note = response.json()
    for visibility in ("all", "global", "none"):
        updated = await client.patch(
            f"/api/v1/notes/{note['id']}",
            json={"agent_visibility": visibility},
        )
        assert updated.status_code == 200
        assert updated.json()["agent_visibility"] == visibility
    listing = await client.get(
        f"/api/v1/projects/{project_id}/notes", params={"document_type": scope}
    )
    assert listing.status_code == 200, listing.text
    assert listing.json()["categories"][0]["id"] == folder["id"]
    assert (await client.delete(f"/api/v1/folders/{folder['id']}")).status_code == 204
    restored = (await client.get(f"/api/v1/notes/{note['id']}")).json()
    assert restored["category_id"] is None
    assert restored["content"] == note["content"]
    assert restored["agent_visibility"] == "none"


@pytest.mark.asyncio
async def test_folder_delete_returns_items_to_default_folder(client: AsyncClient) -> None:
    project_response = await client.post("/api/v1/projects", data={"title": "文件夹测试"})
    project_id = project_response.json()["id"]
    character_response = await client.post(
        f"/api/v1/projects/{project_id}/characters",
        data={"name": "角色", "description": ""},
    )
    character_id = character_response.json()["id"]

    folder_response = await client.post(
        f"/api/v1/projects/{project_id}/folders",
        json={"scope": "character", "title": "主要角色"},
    )
    assert folder_response.status_code == 201
    folder_id = folder_response.json()["id"]

    move_response = await client.post(
        f"/api/v1/projects/{project_id}/folders/items/move",
        json={"scope": "character", "item_id": character_id, "folder_id": folder_id},
    )
    assert move_response.status_code == 204
    assert (await client.get(f"/api/v1/characters/{character_id}")).json()["folder_id"] == folder_id

    delete_response = await client.delete(f"/api/v1/folders/{folder_id}")
    assert delete_response.status_code == 204
    assert (await client.get(f"/api/v1/characters/{character_id}")).json()["folder_id"] is None
