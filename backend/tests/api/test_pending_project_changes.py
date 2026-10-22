"""待审项目变更 API 测试。"""

import pytest
from httpx import AsyncClient

from app.storage.services import (
    note_service,
)
from tests.api.pending_helpers import (
    _create_payload,
    _create_project,
    _post_change,
    _update_payload,
)


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


async def test_revision_is_project_scoped_and_rejected_drafts_are_closed(client):
    project = await _create_project(client, "提案归属")
    other = await _create_project(client, "其他项目")
    original = await _post_change(client, project, _create_payload())
    payload = {"expected_updated_at": original["updated_at"], "patch": {"title": "修改"}}
    assert (
        await client.patch(
            f"/api/v1/projects/{other}/pending-changes/{original['id']}", json=payload
        )
    ).status_code == 404
    url = f"/api/v1/projects/{project}/pending-changes/{original['id']}"
    await client.post(url + "/reject")
    assert (await client.patch(url, json=payload)).status_code == 409
