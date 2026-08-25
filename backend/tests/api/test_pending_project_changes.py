"""待审项目变更 API 测试。"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.storage.models.pending_project_change import PendingProjectChange


async def _create_project(client: AsyncClient, title: str) -> str:
    response = await client.post("/api/v1/projects", data={"title": title})
    assert response.status_code == 201
    return response.json()["id"]


def _change_payload(target_type: str = "note") -> dict:
    return {
        "target_type": target_type,
        "target_id": "note-1",
        "operation": "update",
        "base_hash": "sha256:old",
        "before": {"title": "旧标题", "tags": ["a"]},
        "after": {"title": "新标题", "tags": ["a", "b"]},
        "source_task_id": "task-1",
        "source_message_id": "message-1",
        "model_id": "model-1",
    }


@pytest.mark.asyncio
async def test_pending_change_requires_existing_project(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/projects/missing-project/pending-changes",
        json=_change_payload(),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_pending_change_operation_is_strict_enum(client: AsyncClient) -> None:
    project_id = await _create_project(client, "枚举项目")
    payload = _change_payload()
    payload["operation"] = "archive"
    response = await client.post(
        f"/api/v1/projects/{project_id}/pending-changes",
        json=payload,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_pending_change_create_list_and_detail(client: AsyncClient) -> None:
    project_id = await _create_project(client, "待审项目")

    create_response = await client.post(
        f"/api/v1/projects/{project_id}/pending-changes",
        json=_change_payload(),
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["project_id"] == project_id
    assert created["operation"] == "update"
    assert created["status"] == "pending"
    assert created["applied_at"] is None
    assert created["before"]["title"] == "旧标题"

    list_response = await client.get(f"/api/v1/projects/{project_id}/pending-changes")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [created["id"]]

    detail_response = await client.get(
        f"/api/v1/projects/{project_id}/pending-changes/{created['id']}"
    )
    assert detail_response.status_code == 200
    assert detail_response.json() == created


@pytest.mark.asyncio
async def test_pending_change_project_isolation_and_cross_project_404(
    client: AsyncClient,
) -> None:
    project_a = await _create_project(client, "项目 A")
    project_b = await _create_project(client, "项目 B")
    create_response = await client.post(
        f"/api/v1/projects/{project_a}/pending-changes",
        json=_change_payload("chapter"),
    )
    change_id = create_response.json()["id"]

    project_a_items = await client.get(f"/api/v1/projects/{project_a}/pending-changes")
    project_b_items = await client.get(f"/api/v1/projects/{project_b}/pending-changes")
    assert [item["id"] for item in project_a_items.json()] == [change_id]
    assert project_b_items.json() == []

    cross_project_detail = await client.get(
        f"/api/v1/projects/{project_b}/pending-changes/{change_id}"
    )
    assert cross_project_detail.status_code == 404


@pytest.mark.asyncio
async def test_pending_change_reject(client: AsyncClient) -> None:
    project_id = await _create_project(client, "拒绝项目")
    create_response = await client.post(
        f"/api/v1/projects/{project_id}/pending-changes",
        json=_change_payload(),
    )
    change_id = create_response.json()["id"]

    reject_response = await client.post(
        f"/api/v1/projects/{project_id}/pending-changes/{change_id}/reject"
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "rejected"

    repeat_response = await client.post(
        f"/api/v1/projects/{project_id}/pending-changes/{change_id}/reject"
    )
    assert repeat_response.status_code == 200
    assert repeat_response.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_pending_change_status_filter_and_count(client: AsyncClient) -> None:
    project_a = await _create_project(client, "状态项目 A")
    project_b = await _create_project(client, "状态项目 B")
    first_response = await client.post(
        f"/api/v1/projects/{project_a}/pending-changes",
        json=_change_payload("chapter"),
    )
    second_response = await client.post(
        f"/api/v1/projects/{project_a}/pending-changes",
        json=_change_payload("character"),
    )
    await client.post(
        f"/api/v1/projects/{project_b}/pending-changes",
        json=_change_payload("location"),
    )
    rejected_change_id = second_response.json()["id"]
    reject_response = await client.post(
        f"/api/v1/projects/{project_a}/pending-changes/{rejected_change_id}/reject"
    )
    assert reject_response.status_code == 200

    pending_response = await client.get(
        f"/api/v1/projects/{project_a}/pending-changes",
        params={"status": "pending"},
    )
    rejected_response = await client.get(
        f"/api/v1/projects/{project_a}/pending-changes",
        params={"status": "rejected"},
    )
    assert [item["id"] for item in pending_response.json()] == [
        first_response.json()["id"]
    ]
    assert [item["id"] for item in rejected_response.json()] == [rejected_change_id]

    default_count_response = await client.get(
        f"/api/v1/projects/{project_a}/pending-changes/count"
    )
    rejected_count_response = await client.get(
        f"/api/v1/projects/{project_a}/pending-changes/count",
        params={"status": "rejected"},
    )
    project_b_count_response = await client.get(
        f"/api/v1/projects/{project_b}/pending-changes/count"
    )
    assert default_count_response.json() == {"count": 1}
    assert rejected_count_response.json() == {"count": 1}
    assert project_b_count_response.json() == {"count": 1}


@pytest.mark.asyncio
async def test_pending_change_status_is_strict_enum(client: AsyncClient) -> None:
    project_id = await _create_project(client, "状态枚举项目")

    applied_list_response = await client.get(
        f"/api/v1/projects/{project_id}/pending-changes",
        params={"status": "applied"},
    )
    list_response = await client.get(
        f"/api/v1/projects/{project_id}/pending-changes",
        params={"status": "unknown"},
    )
    count_response = await client.get(
        f"/api/v1/projects/{project_id}/pending-changes/count",
        params={"status": "unknown"},
    )
    assert applied_list_response.status_code == 200
    assert applied_list_response.json() == []
    assert list_response.status_code == 422
    assert count_response.status_code == 422


@pytest.mark.asyncio
async def test_pending_change_deleted_with_project(
    client: AsyncClient, session
) -> None:
    project_id = await _create_project(client, "级联项目")
    create_response = await client.post(
        f"/api/v1/projects/{project_id}/pending-changes",
        json=_change_payload(),
    )
    change_id = create_response.json()["id"]

    delete_response = await client.delete(f"/api/v1/projects/{project_id}")
    assert delete_response.status_code == 204

    result = await session.execute(
        select(PendingProjectChange).where(PendingProjectChange.id == change_id)
    )
    assert result.scalar_one_or_none() is None
