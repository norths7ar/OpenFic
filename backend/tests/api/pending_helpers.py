"""Shared setup for pending proposal API scenarios."""

from httpx import AsyncClient


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
