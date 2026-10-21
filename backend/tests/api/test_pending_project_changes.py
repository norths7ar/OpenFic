"""待审项目变更 API 测试。"""

import pytest
from httpx import AsyncClient

from app.storage.services import (
    note_service,
)


async def _create_project(client: AsyncClient, title: str) -> str:
    response = await client.post("/api/v1/projects", data={"title": title})
    assert response.status_code == 201
    return response.json()["id"]


def _create_payload(
    target_type: str = "note",
    *,
    after: dict | None = None,
) -> dict:
    return {
        "target_type": target_type,
        "operation": "create",
        "after": after or {"title": "新资料", "body": "候审内容"},
        "source_task_id": "task-1",
        "source_message_id": "message-1",
        "model_id": "model-1",
    }


def _update_payload(target_type: str, target_id: str, after: dict) -> dict:
    return {
        "target_type": target_type,
        "target_id": target_id,
        "operation": "update",
        "after": after,
    }


async def _post_change(client: AsyncClient, project_id: str, payload: dict) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/pending-changes",
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_pending_change_project_isolation_and_cross_project_404(
    client: AsyncClient,
) -> None:
    project_a = await _create_project(client, "项目 A")
    project_b = await _create_project(client, "项目 B")
    created = await _post_change(client, project_a, _create_payload("character"))

    project_a_items = await client.get(f"/api/v1/projects/{project_a}/pending-changes")
    project_b_items = await client.get(f"/api/v1/projects/{project_b}/pending-changes")
    cross_project_detail = await client.get(
        f"/api/v1/projects/{project_b}/pending-changes/{created['id']}"
    )
    assert [item["id"] for item in project_a_items.json()] == [created["id"]]
    assert project_b_items.json() == []
    assert cross_project_detail.status_code == 404


@pytest.mark.asyncio
async def test_pending_change_target_cannot_cross_projects(
    client: AsyncClient,
    session,
) -> None:
    project_a = await _create_project(client, "对象项目 A")
    project_b = await _create_project(client, "对象项目 B")
    note = await note_service.create_note(session, project_a, None, "A 的笔记", "正文")
    await session.commit()
    response = await client.post(
        f"/api/v1/projects/{project_b}/pending-changes",
        json=_update_payload("note", note.id, {"body": "越权修改"}),
    )
    assert response.status_code == 404
