import pytest
from httpx import AsyncClient


async def _project(client: AsyncClient, title: str) -> str:
    response = await client.post("/api/v1/projects", data={"title": title})
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.asyncio
async def test_reorder_rejects_cross_project_id_and_wrong_parent(
    client: AsyncClient,
) -> None:
    first_project = await _project(client, "项目一")
    second_project = await _project(client, "项目二")
    character = await client.post(
        f"/api/v1/projects/{second_project}/characters", data={"name": "外部角色"}
    )
    response = await client.post(
        f"/api/v1/projects/{first_project}/characters/reorder",
        json={"ordered_ids": [character.json()["id"]]},
    )
    assert response.status_code == 400

    response = await client.post(
        f"/api/v1/projects/{first_project}/note-items/reorder",
        json={"kind": "note", "parent_id": "foreign-category", "ordered_ids": []},
    )
    assert response.status_code == 400
