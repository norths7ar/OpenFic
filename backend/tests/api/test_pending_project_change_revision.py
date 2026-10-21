"""Draft revision and conservative quote matching regressions."""


from tests.api.test_pending_project_changes import (
    _create_payload,
    _create_project,
    _post_change,
)


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
