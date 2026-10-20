"""角色 API 测试。"""


import pytest
from httpx import AsyncClient


async def create_project(client: AsyncClient, title: str) -> str:
    response = await client.post("/api/v1/projects", data={"title": title})
    assert response.status_code == 201
    return response.json()["id"]


async def create_character(
    client: AsyncClient,
    project_id: str,
    name: str,
    description: str = "",
    image: bytes | None = None,
) -> dict:
    files = None
    if image is not None:
        files = {"image": ("avatar.png", image, "image/png")}
    response = await client.post(
        f"/api/v1/projects/{project_id}/characters",
        data={"name": name, "description": description},
        files=files,
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_update_character_writing_visibility(client: AsyncClient) -> None:
    project_id = await create_project(client, "写作可见性项目")
    character = await create_character(client, project_id, "暂不登场角色")

    response = await client.patch(
        f"/api/v1/characters/{character['id']}",
        data={"agent_visibility": "global"},
    )

    assert response.status_code == 200
    assert response.json()["agent_visibility"] == "global"


@pytest.mark.asyncio
async def test_character_visibility_rejects_unknown_state(client: AsyncClient) -> None:
    project_id = await create_project(client, "Visibility validation")
    character = await create_character(client, project_id, "Character")
    response = await client.patch(
        f"/api/v1/characters/{character['id']}", data={"agent_visibility": "invalid"}
    )
    assert response.status_code == 422
