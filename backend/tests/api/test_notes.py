"""Note API 端点测试。"""

import pytest
from httpx import AsyncClient


async def _create_project(client: AsyncClient) -> tuple[str, str]:
    response = await client.post(
        "/api/v1/projects",
        data={"title": "测试小说"},
    )
    assert response.status_code == 201
    project_id = response.json()["id"]
    volumes = (await client.get(f"/api/v1/projects/{project_id}/volumes")).json()
    assert len(volumes) == 1
    return project_id, volumes[0]["id"]


@pytest.mark.asyncio
async def test_update_note_agent_visibility_atomically(client: AsyncClient) -> None:
    project_id, _ = await _create_project(client)
    create = await client.post(
        f"/api/v1/projects/{project_id}/notes",
        json={"title": "后续伏笔", "content": "暂不进入写作上下文"},
    )
    note_id = create.json()["id"]

    response = await client.patch(
        f"/api/v1/notes/{note_id}",
        json={"agent_visibility": "none"},
    )

    assert response.status_code == 200
    assert response.json()["agent_visibility"] == "none"


@pytest.mark.asyncio
async def test_update_note_rejects_content_over_line_limit(client: AsyncClient) -> None:
    project_id, _ = await _create_project(client)
    create = await client.post(
        f"/api/v1/projects/{project_id}/notes",
        json={"title": "原笔记", "content": "原内容"},
    )
    note_id = create.json()["id"]

    response = await client.patch(
        f"/api/v1/notes/{note_id}",
        json={"content": "\n".join("内容" for _ in range(2001))},
    )

    assert response.status_code == 400
    assert "内容超出限制" in response.json()["detail"]
    unchanged = await client.get(f"/api/v1/notes/{note_id}")
    assert unchanged.json()["content"] == "原内容"


@pytest.mark.asyncio
async def test_mentions_hidden_note_absent(client: AsyncClient) -> None:
    project_id, _ = await _create_project(client)
    note = await client.post(
        f"/api/v1/projects/{project_id}/notes",
        json={"title": "隐藏笔记", "content": ""},
    )
    note_id = note.json()["id"]
    await client.patch(
        f"/api/v1/notes/{note_id}",
        json={"agent_visibility": "none"},
    )
    resp = await client.get(
        f"/api/v1/projects/{project_id}/mentions",
        params={"query": "隐藏"},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert not any(item["kind"] == "note" and item["title"] == "隐藏笔记" for item in items)


@pytest.mark.asyncio
async def test_note_visibility_rejects_unknown_state(client: AsyncClient) -> None:
    project_id, _ = await _create_project(client)
    note = await client.post(f"/api/v1/projects/{project_id}/notes", json={"title": "Visibility"})
    response = await client.patch(
        f"/api/v1/notes/{note.json()['id']}", json={"agent_visibility": "invalid"}
    )
    assert response.status_code == 422
