"""
WorldInfo Entry API 测试。
"""


import pytest
from httpx import AsyncClient


@pytest.fixture
async def world_info_id(client: AsyncClient) -> str:
    """创建项目并返回项目唯一世界书 ID。"""
    project_resp = await client.post(
        "/api/v1/projects",
        data={"title": "测试小说"},
    )
    project_id = project_resp.json()["id"]
    world_info_resp = await client.get(f"/api/v1/projects/{project_id}/world-info")
    return world_info_resp.json()["id"]


@pytest.mark.asyncio
async def test_world_visibility_rejects_unknown_state(
    client: AsyncClient, world_info_id: str
) -> None:
    entry = await client.post(
        f"/api/v1/world-info/{world_info_id}/entries", json={"name": "Visibility"}
    )
    response = await client.patch(
        f"/api/v1/world-info-entries/{entry.json()['id']}", json={"agent_visibility": "invalid"}
    )
    assert response.status_code == 422
