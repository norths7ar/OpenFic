"""Shared project-folder behavior."""

import pytest
from httpx import AsyncClient


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
