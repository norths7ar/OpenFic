"""Review one evolving draft against current material before adopting a version."""

import pytest

from tests.api.pending_helpers import _create_project


async def _start_review(client):
    project = await _create_project(client, "沈照微的待审故事")
    response = await client.post(
        f"/api/v1/projects/{project}/notes",
        json={"title": "原稿", "content": "她离开圣域。", "agent_visibility": "all"},
    )
    assert response.status_code == 201, response.text
    note = response.json()
    collection = f"/api/v1/projects/{project}/pending-changes"
    response = await client.post(
        collection,
        json={
            "target_type": "note",
            "target_id": note["id"],
            "operation": "update",
            "after": {"title": "求援草稿", "body": "她决定求援，通知戒律司。"},
        },
    )
    assert response.status_code == 201, response.text
    draft = response.json()
    return project, f"/api/v1/notes/{note['id']}", f"{collection}/{draft['id']}", draft


def _confirmation(review, revision_id=None):
    return {
        "expected_updated_at": review["updated_at"],
        "expected_current_hash": review["current_hash"],
        "revision_id": revision_id or review["current_revision_id"],
    }


async def test_revise_one_draft_then_adopt_selected_history_against_current_material(client):
    project, note_url, url, first = await _start_review(client)
    first_version = first["current_revision_id"]
    revised = await client.patch(
        url,
        json={
            "expected_updated_at": first["updated_at"],
            "patch": {
                "title": "自愿求援",
                "agent_visibility": "global",
                "edits": [{"old_content": "戒律司", "new_content": "飞瑶"}],
            },
        },
    )
    assert revised.status_code == 200, revised.text
    second = revised.json()
    assert second["id"] == first["id"]
    assert second["after"]["body"] == "她决定求援，通知飞瑶。"
    assert second["after"]["title"] == "自愿求援"
    assert second["after"]["agent_visibility"] == "global"
    assert second["before"] == first["before"]
    assert (await client.get(note_url)).json()["content"] == "她离开圣域。"

    history = (await client.get(url + "/revisions")).json()
    assert len(history) == 2
    versions = {item["id"]: item["after"] for item in history}
    assert versions[first_version] == first["after"]
    assert versions[second["current_revision_id"]] == second["after"]
    selected = (await client.get(url + f"/revisions/{first_version}")).json()
    assert selected["after"] == first["after"]
    assert (await client.get(url)).json()["after"] == second["after"]

    updated = await client.patch(
        note_url, json={"title": "正式稿新标题", "content": "正式稿后来增加了另一段。"}
    )
    assert updated.status_code == 200, updated.text
    review = (await client.get(url)).json()
    assert review["current"]["body"] == "正式稿后来增加了另一段。"
    assert review["current"]["title"] == "正式稿新标题"
    assert review["current_hash"] != first["current_hash"]
    assert review["before"] == first["before"]
    assert review["is_applicable"] is True

    adopted = await client.post(url + "/apply", json=_confirmation(review, first_version))
    assert adopted.status_code == 200, adopted.text
    assert adopted.json()["applied_revision_id"] == first_version
    assert adopted.json()["status"] == "applied"
    actual = (await client.get(note_url)).json()
    assert (actual["title"], actual["content"], actual["agent_visibility"]) == (
        "求援草稿",
        "她决定求援，通知戒律司。",
        "all",
    )
    history_url = f"/api/v1/projects/{project}/documents/note/{actual['id']}/history"
    formal_versions = (await client.get(history_url)).json()["items"]
    details = [(await client.get(f"{history_url}/{item['id']}")).json() for item in formal_versions]
    assert any(
        item["title"] == "正式稿新标题" and item["content"] == "正式稿后来增加了另一段。"
        for item in details
    )
    assert {v["id"]: v["after"] for v in (await client.get(url + "/revisions")).json()} == versions


@pytest.mark.parametrize("changed_side", ["formal", "draft"])
async def test_review_must_be_repeated_when_either_side_changes(client, changed_side):
    _, note_url, url, reviewed = await _start_review(client)
    assert (await client.post(url + "/apply", json={})).status_code == 422
    if changed_side == "formal":
        changed = await client.patch(note_url, json={"content": "用户尚未审阅的新正文。"})
        assert changed.status_code == 200, changed.text
    else:
        changed = await client.patch(
            url,
            json={"expected_updated_at": reviewed["updated_at"], "patch": {"body": "新版右侧。"}},
        )
        assert changed.status_code == 200, changed.text
        stale_save = await client.patch(
            url,
            json={"expected_updated_at": reviewed["updated_at"], "patch": {"body": "过期编辑。"}},
        )
        assert stale_save.status_code == 409
        assert (await client.get(url)).json()["after"]["body"] == "新版右侧。"

    expected_content = (await client.get(note_url)).json()["content"]
    expected_draft = (await client.get(url)).json()["after"]
    result = await client.post(url + "/apply", json=_confirmation(reviewed))
    assert result.status_code == 409, result.text
    assert (await client.get(note_url)).json()["content"] == expected_content
    current = (await client.get(url)).json()
    assert current["status"] == "pending"
    assert current["after"] == expected_draft

    confirmed = await client.post(url + "/apply", json=_confirmation(current))
    assert confirmed.status_code == 200, confirmed.text
    assert (await client.get(note_url)).json()["content"] == expected_draft["body"]


async def test_deleted_material_cannot_be_recreated_by_adopting_an_update(client):
    _, note_url, url, reviewed = await _start_review(client)
    assert (await client.delete(note_url)).status_code == 204
    current = (await client.get(url)).json()
    assert current["current"] is None
    assert current["is_applicable"] is False
    result = await client.post(url + "/apply", json=_confirmation(current))
    assert result.status_code == 409, result.text
    assert (await client.get(note_url)).status_code == 404
    remaining = (await client.get(url)).json()
    assert remaining["status"] == "pending"
    assert remaining["after"] == reviewed["after"]
