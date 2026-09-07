"""待审项目变更 API 测试。"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.storage.models.character import Character
from app.storage.models.note import Note
from app.storage.models.pending_project_change import PendingProjectChange
from app.storage.models.project_folder import ProjectFolder as NoteCategory
from app.storage.models.world_info_entry import WorldInfoEntry
from app.storage.repos import pending_project_change_repo
from app.storage.services import (
    character_service,
    note_service,
    world_info_entry_service,
    world_info_service,
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
async def test_pending_change_requires_existing_project(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/projects/missing-project/pending-changes",
        json=_create_payload(),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_pending_change_request_contract_is_strict(client: AsyncClient) -> None:
    project_id = await _create_project(client, "枚举项目")
    invalid_operation = _create_payload()
    invalid_operation["operation"] = "archive"
    invalid_target = _create_payload("chapter")
    injected_field = _create_payload("character")
    injected_field["after"]["order"] = 99

    operation_response = await client.post(
        f"/api/v1/projects/{project_id}/pending-changes",
        json=invalid_operation,
    )
    target_response = await client.post(
        f"/api/v1/projects/{project_id}/pending-changes",
        json=invalid_target,
    )
    field_response = await client.post(
        f"/api/v1/projects/{project_id}/pending-changes",
        json=injected_field,
    )
    assert operation_response.status_code == 422
    assert target_response.status_code == 422
    assert field_response.status_code == 422


@pytest.mark.asyncio
async def test_pending_change_create_list_and_detail(client: AsyncClient) -> None:
    project_id = await _create_project(client, "待审项目")
    created = await _post_change(client, project_id, _create_payload())

    assert created["project_id"] == project_id
    assert created["operation"] == "create"
    assert created["status"] == "pending"
    assert created["applied_at"] is None
    assert created["base_hash"] is None
    assert created["before"] is None
    assert created["after"]["kind"] == "note"
    assert created["is_applicable"] is True
    assert created["applicability_reason"] is None

    list_response = await client.get(f"/api/v1/projects/{project_id}/pending-changes")
    detail_response = await client.get(
        f"/api/v1/projects/{project_id}/pending-changes/{created['id']}"
    )
    assert [item["id"] for item in list_response.json()] == [created["id"]]
    assert detail_response.json() == created


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
async def test_pending_change_reject_is_idempotent(client: AsyncClient) -> None:
    project_id = await _create_project(client, "拒绝项目")
    created = await _post_change(client, project_id, _create_payload())
    url = f"/api/v1/projects/{project_id}/pending-changes/{created['id']}/reject"

    reject_response = await client.post(url)
    repeat_response = await client.post(url)
    assert reject_response.json()["status"] == "rejected"
    assert repeat_response.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_pending_change_status_filter_and_count(client: AsyncClient) -> None:
    project_a = await _create_project(client, "状态项目 A")
    project_b = await _create_project(client, "状态项目 B")
    first = await _post_change(client, project_a, _create_payload("note"))
    second = await _post_change(client, project_a, _create_payload("character"))
    await _post_change(client, project_b, _create_payload("world_entry"))
    await client.post(f"/api/v1/projects/{project_a}/pending-changes/{second['id']}/reject")

    pending_response = await client.get(
        f"/api/v1/projects/{project_a}/pending-changes",
        params={"status": "pending"},
    )
    rejected_response = await client.get(
        f"/api/v1/projects/{project_a}/pending-changes",
        params={"status": "rejected"},
    )
    default_count_response = await client.get(f"/api/v1/projects/{project_a}/pending-changes/count")
    rejected_count_response = await client.get(
        f"/api/v1/projects/{project_a}/pending-changes/count",
        params={"status": "rejected"},
    )
    assert [item["id"] for item in pending_response.json()] == [first["id"]]
    assert [item["id"] for item in rejected_response.json()] == [second["id"]]
    assert default_count_response.json() == {"count": 1}
    assert rejected_count_response.json() == {"count": 1}


@pytest.mark.asyncio
async def test_pending_change_status_is_strict_enum(client: AsyncClient) -> None:
    project_id = await _create_project(client, "状态枚举项目")
    applied_response = await client.get(
        f"/api/v1/projects/{project_id}/pending-changes",
        params={"status": "applied"},
    )
    invalid_response = await client.get(
        f"/api/v1/projects/{project_id}/pending-changes",
        params={"status": "unknown"},
    )
    assert applied_response.status_code == 200
    assert applied_response.json() == []
    assert invalid_response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target_type", "after"),
    [
        (
            "note",
            {
                "title": "候审笔记",
                "body": "笔记正文",
                "writing_visible": False,
            },
        ),
        ("note_category", {"title": "候审分类"}),
        (
            "character",
            {
                "title": "候审角色",
                "body": "角色描述",
                "writing_visible": False,
            },
        ),
        (
            "world_entry",
            {
                "title": "候审设定",
                "body": "设定正文",
                "section": "地理",
                "writing_visible": False,
            },
        ),
    ],
)
async def test_apply_create_supported_targets(
    client: AsyncClient,
    session,
    target_type: str,
    after: dict,
) -> None:
    project_id = await _create_project(client, f"创建 {target_type}")
    created = await _post_change(
        client,
        project_id,
        _create_payload(target_type, after=after),
    )

    response = await client.post(
        f"/api/v1/projects/{project_id}/pending-changes/{created['id']}/apply"
    )
    assert response.status_code == 200, response.text
    applied = response.json()
    assert applied["status"] == "applied"
    assert applied["applied_at"] is not None
    assert applied["target_id"]
    assert applied["after"]["kind"] == target_type

    model = {
        "note": Note,
        "note_category": NoteCategory,
        "character": Character,
        "world_entry": WorldInfoEntry,
    }[target_type]
    stored = await session.get(model, applied["target_id"])
    assert stored is not None
    if target_type == "note":
        assert stored.content == "笔记正文"
        assert stored.is_writing_visible is False
    elif target_type == "character":
        assert stored.description == "角色描述"
        assert stored.is_writing_visible is False
    elif target_type == "world_entry":
        assert stored.content == "设定正文"
        assert stored.section == "地理"
        assert stored.is_enabled is False
        assert stored.token_count > 0


@pytest.mark.asyncio
async def test_pending_change_accepts_matching_tool_payload_kind(
    client: AsyncClient,
) -> None:
    project_id = await _create_project(client, "工具判别字段项目")
    category_response = await client.post(
        f"/api/v1/projects/{project_id}/note-categories",
        json={"title": "原分类"},
    )
    category_id = category_response.json()["id"]
    note_response = await client.post(
        f"/api/v1/projects/{project_id}/notes",
        json={
            "category_id": category_id,
            "title": "原笔记",
            "content": "原正文",
        },
    )
    note_id = note_response.json()["id"]

    accepted = await client.post(
        f"/api/v1/projects/{project_id}/pending-changes",
        json=_update_payload(
            "note",
            note_id,
            {"kind": "note", "title": "更新笔记", "body": "候审正文"},
        ),
    )
    rejected = await client.post(
        f"/api/v1/projects/{project_id}/pending-changes",
        json=_update_payload(
            "note",
            note_id,
            {"kind": "character", "title": "错误类型"},
        ),
    )

    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["after"]["kind"] == "note"
    assert accepted.json()["after"]["body"] == "候审正文"
    assert accepted.json()["after"]["category_id"] == category_id
    assert rejected.status_code == 422
    assert "after.kind 必须与 target_type 一致" in rejected.text


@pytest.mark.asyncio
async def test_apply_update_captures_base_and_rejects_stale_target(
    client: AsyncClient,
) -> None:
    project_id = await _create_project(client, "冲突项目")
    note_response = await client.post(
        f"/api/v1/projects/{project_id}/notes",
        json={"title": "原笔记", "content": "原正文"},
    )
    note_id = note_response.json()["id"]
    change = await _post_change(
        client,
        project_id,
        _update_payload("note", note_id, {"body": "候审正文"}),
    )
    assert change["base_hash"].startswith("sha256:")
    assert change["before"]["body"] == "原正文"
    assert change["after"]["body"] == "候审正文"

    mutate_response = await client.patch(
        f"/api/v1/notes/{note_id}",
        json={"content": "用户随后修改的正文"},
    )
    assert mutate_response.status_code == 200
    apply_response = await client.post(
        f"/api/v1/projects/{project_id}/pending-changes/{change['id']}/apply"
    )
    assert apply_response.status_code == 409
    assert apply_response.json()["detail"]["code"] == "pending_change_conflict"

    detail = await client.get(f"/api/v1/projects/{project_id}/pending-changes/{change['id']}")
    note = await client.get(f"/api/v1/notes/{note_id}")
    assert detail.json()["status"] == "pending"
    assert detail.json()["is_applicable"] is False
    assert "发生变化" in detail.json()["applicability_reason"]
    assert note.json()["content"] == "用户随后修改的正文"


@pytest.mark.asyncio
async def test_locked_note_change_reports_not_applicable(
    client: AsyncClient,
) -> None:
    project_id = await _create_project(client, "锁定候审项目")
    note_response = await client.post(
        f"/api/v1/projects/{project_id}/notes",
        json={"title": "原笔记", "content": "原正文"},
    )
    note_id = note_response.json()["id"]
    lock_response = await client.patch(
        f"/api/v1/notes/{note_id}/lock",
        json={"is_locked": True},
    )
    change = await _post_change(
        client,
        project_id,
        _update_payload("note", note_id, {"body": "候审正文"}),
    )
    detail_response = await client.get(
        f"/api/v1/projects/{project_id}/pending-changes/{change['id']}"
    )

    assert lock_response.status_code == 200
    assert detail_response.status_code == 200
    assert detail_response.json()["is_applicable"] is False
    assert "锁定" in detail_response.json()["applicability_reason"]


@pytest.mark.asyncio
async def test_apply_update_is_one_time_and_applied_change_cannot_be_rejected(
    client: AsyncClient,
) -> None:
    project_id = await _create_project(client, "采用项目")
    note_response = await client.post(
        f"/api/v1/projects/{project_id}/notes",
        json={"title": "原笔记", "content": "原正文"},
    )
    note_id = note_response.json()["id"]
    change = await _post_change(
        client,
        project_id,
        _update_payload(
            "note",
            note_id,
            {"title": "采用后的标题", "body": "采用后的正文"},
        ),
    )
    apply_url = f"/api/v1/projects/{project_id}/pending-changes/{change['id']}/apply"
    reject_url = f"/api/v1/projects/{project_id}/pending-changes/{change['id']}/reject"

    first = await client.post(apply_url)
    repeat = await client.post(apply_url)
    reject = await client.post(reject_url)
    note = await client.get(f"/api/v1/notes/{note_id}")
    assert first.status_code == 200
    assert repeat.status_code == 409
    assert reject.status_code == 409
    assert note.json()["title"] == "采用后的标题"
    assert note.json()["content"] == "采用后的正文"


@pytest.mark.asyncio
async def test_pending_change_claim_is_atomic(
    client: AsyncClient,
    session,
) -> None:
    project_id = await _create_project(client, "原子领取项目")
    created = await _post_change(client, project_id, _create_payload())

    first = await pending_project_change_repo.claim_for_apply(
        session,
        project_id,
        created["id"],
    )
    second = await pending_project_change_repo.claim_for_apply(
        session,
        project_id,
        created["id"],
    )
    stored = await pending_project_change_repo.get_by_id(
        session,
        project_id,
        created["id"],
    )
    assert first is True
    assert second is False
    assert stored is not None
    assert stored.status == "applying"


@pytest.mark.asyncio
async def test_legacy_pending_change_remains_reviewable_but_cannot_apply(
    client: AsyncClient,
    session,
) -> None:
    project_id = await _create_project(client, "旧候审记录项目")
    legacy = PendingProjectChange(
        project_id=project_id,
        target_type="legacy_target",
        target_id="legacy-id",
        operation="update",
        before={"title": "旧值"},
        after={"title": "新值"},
        status="pending",
    )
    session.add(legacy)
    await session.flush()

    apply_response = await client.post(
        f"/api/v1/projects/{project_id}/pending-changes/{legacy.id}/apply"
    )
    detail_response = await client.get(f"/api/v1/projects/{project_id}/pending-changes/{legacy.id}")
    assert apply_response.status_code == 422
    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize("target_type", ["note", "character", "world_entry"])
async def test_apply_delete_supported_targets(
    client: AsyncClient,
    session,
    target_type: str,
) -> None:
    project_id = await _create_project(client, f"删除 {target_type}")
    if target_type == "note":
        target = await note_service.create_note(session, project_id, None, "待删笔记", "正文")
    elif target_type == "character":
        target = await character_service.create_character(session, project_id, "待删角色")
    else:
        world_info = await world_info_service.get_or_create_world_info_by_project(
            session, project_id
        )
        target = await world_info_entry_service.create_entry(
            session,
            world_info.id,
            "待删设定",
        )
    await session.commit()

    change = await _post_change(
        client,
        project_id,
        {
            "target_type": target_type,
            "target_id": target.id,
            "operation": "delete",
            "after": None,
        },
    )
    response = await client.post(
        f"/api/v1/projects/{project_id}/pending-changes/{change['id']}/apply"
    )
    assert response.status_code == 200, response.text
    assert await session.get(type(target), target.id) is None


@pytest.mark.asyncio
async def test_note_category_delete_is_not_supported(client: AsyncClient, session) -> None:
    project_id = await _create_project(client, "分类删除")
    category = await note_service.create_category(session, project_id, None, "不可级联删除")
    await session.commit()
    response = await client.post(
        f"/api/v1/projects/{project_id}/pending-changes",
        json={
            "target_type": "note_category",
            "target_id": category.id,
            "operation": "delete",
            "after": None,
        },
    )
    assert response.status_code == 422
    assert await session.get(NoteCategory, category.id) is not None


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


@pytest.mark.asyncio
async def test_apply_create_rejects_silent_name_rewrite(
    client: AsyncClient,
    session,
) -> None:
    project_id = await _create_project(client, "重名项目")
    await character_service.create_character(session, project_id, "同名角色")
    await session.commit()
    change = await _post_change(
        client,
        project_id,
        _create_payload("character", after={"title": "  同名角色  "}),
    )
    assert change["after"]["title"] == "同名角色"
    response = await client.post(
        f"/api/v1/projects/{project_id}/pending-changes/{change['id']}/apply"
    )
    assert response.status_code == 409
    detail = await client.get(f"/api/v1/projects/{project_id}/pending-changes/{change['id']}")
    assert detail.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_pending_character_change_rejects_blank_name(
    client: AsyncClient,
) -> None:
    project_id = await _create_project(client, "空角色名项目")
    response = await client.post(
        f"/api/v1/projects/{project_id}/pending-changes",
        json=_create_payload("character", after={"title": "   "}),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_pending_change_deleted_with_project(
    client: AsyncClient,
    session,
) -> None:
    project_id = await _create_project(client, "级联项目")
    change = await _post_change(client, project_id, _create_payload())
    delete_response = await client.delete(f"/api/v1/projects/{project_id}")
    assert delete_response.status_code == 204

    result = await session.execute(
        select(PendingProjectChange).where(PendingProjectChange.id == change["id"])
    )
    assert result.scalar_one_or_none() is None
