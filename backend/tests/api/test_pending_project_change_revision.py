"""Draft revision and conservative quote matching regressions."""

import pytest

from tests.api.test_pending_project_changes import (
    _create_payload,
    _create_project,
    _post_change,
)


@pytest.mark.parametrize("target", ["note", "character", "world_entry", "note_category"])
async def test_revise_create_and_reject_stale_writes(client, target):
    project = await _create_project(client, "修订草稿")
    after = {"title": "初稿"} if target == "note_category" else {"title": "初稿", "body": "半成品"}
    original = await _post_change(client, project, _create_payload(target, after=after))
    url = f"/api/v1/projects/{project}/pending-changes/{original['id']}"
    patch = {"title": "修订版"}
    if target != "note_category":
        patch["edits"] = [{"old_content": "半成品", "new_content": "完成内容"}]
    response = await client.patch(
        url, json={"expected_updated_at": original["updated_at"], "patch": patch}
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["status"] == "pending"
    assert updated["before"] is None and updated["base_hash"] is None
    assert updated["updated_at"] != original["updated_at"]
    for action in ["", "/apply", "/reject"]:
        body = {"expected_updated_at": original["updated_at"]}
        if not action:
            body["patch"] = {"title": "过期覆盖"}
        stale = await client.request("PATCH" if not action else "POST", url + action, json=body)
        assert stale.status_code == 409, stale.text
    assert (await client.get(url)).json()["after"]["title"] == "修订版"
    accepted = await client.post(
        url + "/apply", json={"expected_updated_at": updated["updated_at"]}
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["after"]["title"] == "修订版"
    locked = await client.patch(
        url, json={"expected_updated_at": updated["updated_at"], "patch": {"title": "已采用"}}
    )
    assert locked.status_code == 409


@pytest.mark.parametrize(
    "patch",
    [
        {},
        {"id": "overwrite"},
        {"category_id": None},
        {"body": None},
        {"title": ""},
        {"body": "x", "edits": [{"old_content": "a", "new_content": "b"}]},
    ],
)
async def test_revision_rejects_invalid_fields(client, patch):
    project = await _create_project(client, "修订字段")
    original = await _post_change(client, project, _create_payload())
    url = f"/api/v1/projects/{project}/pending-changes/{original['id']}"
    result = await client.patch(
        url, json={"expected_updated_at": original["updated_at"], "patch": patch}
    )
    assert result.status_code == 422, result.text
    assert (await client.get(url)).json()["after"] == original["after"]


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
