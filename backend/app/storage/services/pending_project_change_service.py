"""待审项目变更业务逻辑层。"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.storage.models.pending_project_change import PendingProjectChange
from app.storage.repos import pending_project_change_repo, project_repo


async def _ensure_project_exists(session: AsyncSession, project_id: str) -> None:
    if await project_repo.get_by_id(session, project_id) is None:
        raise NotFoundError(f"项目不存在: {project_id}")


def proposal_execution_id(
    project_id: str, source_task_id: str | None, source_message_id: str | None, tool_call_id: str
) -> str:
    identity = json.dumps([project_id, source_task_id, source_message_id, tool_call_id])
    return "tool_" + hashlib.sha256(identity.encode()).hexdigest()


async def create_pending_change(
    session: AsyncSession,
    *,
    project_id: str,
    target_type: str,
    target_id: str | None,
    operation: str,
    after: Any,
    source_task_id: str | None,
    source_message_id: str | None,
    model_id: str | None,
    tool_call_id: str | None = None,
) -> PendingProjectChange:
    """创建一条绑定项目、由服务端捕获基础快照的待审变更。"""
    await _ensure_project_exists(session, project_id)
    # Stable execution identity, not content similarity, makes redelivery durable.
    change_id = None
    if tool_call_id:
        change_id = proposal_execution_id(
            project_id, source_task_id, source_message_id, tool_call_id
        )
        existing = await pending_project_change_repo.get_by_id(session, project_id, change_id)
        if existing is not None:
            return existing
    from app.storage.services import pending_project_change_apply_service

    prepared = await pending_project_change_apply_service.prepare_pending_change(
        session,
        project_id=project_id,
        target_type=cast(
            pending_project_change_apply_service.PendingTargetType,
            target_type,
        ),
        target_id=target_id,
        operation=operation,
        after=after,
    )
    change = PendingProjectChange(
        project_id=project_id,
        target_type=target_type,
        target_id=prepared.target_id,
        operation=operation,
        base_hash=prepared.base_hash,
        before=prepared.before,
        after=prepared.after,
        source_task_id=source_task_id,
        source_message_id=source_message_id,
        model_id=model_id,
    )
    if change_id is None:
        return await pending_project_change_repo.create(session, change)
    change.id = change_id
    try:
        async with session.begin_nested():
            return await pending_project_change_repo.create(session, change)
    except IntegrityError:
        existing = await pending_project_change_repo.get_by_id(session, project_id, change_id)
        if existing is None:
            raise
        return existing


async def list_pending_changes(
    session: AsyncSession,
    project_id: str,
    status: str | None = None,
) -> list[PendingProjectChange]:
    """获取项目下的待审变更。"""
    await _ensure_project_exists(session, project_id)
    return await pending_project_change_repo.list_by_project(session, project_id, status)


async def count_pending_changes(
    session: AsyncSession,
    project_id: str,
    status: str,
) -> int:
    """统计项目下指定状态的待审变更。"""
    await _ensure_project_exists(session, project_id)
    return await pending_project_change_repo.count_by_project(session, project_id, status)


async def get_pending_change(
    session: AsyncSession,
    project_id: str,
    change_id: str,
) -> PendingProjectChange:
    """按项目范围获取待审变更详情。"""
    change = await pending_project_change_repo.get_by_id(session, project_id, change_id)
    if change is None:
        raise NotFoundError(f"待审项目变更不存在: {change_id}")
    return change


async def reject_pending_change(
    session: AsyncSession,
    project_id: str,
    change_id: str,
    *,
    expected_updated_at: datetime | None = None,
) -> PendingProjectChange:
    """拒绝待审变更；重复拒绝保持幂等。"""
    change = await get_pending_change(session, project_id, change_id)
    if change.status == "applied":
        raise ConflictError("已采用的变更不能拒绝")
    if change.status == "rejected":
        return change
    expected = expected_updated_at or change.updated_at
    if expected.tzinfo is not None:
        expected = expected.astimezone(UTC).replace(tzinfo=None)
    if not await pending_project_change_repo.reject_if_current(session, change, expected):
        raise ConflictError("提案已变化或不再待审，请重新读取后再拒绝")
    return change


async def revise_pending_change(
    session: AsyncSession,
    project_id: str,
    change_id: str,
    *,
    patch: dict[str, Any],
    expected_updated_at: datetime,
) -> PendingProjectChange:
    """Revise the proposed result without changing its authoritative base."""
    from app.storage.services import pending_project_change_apply_service as apply_service

    change = await get_pending_change(session, project_id, change_id)
    if change.status != "pending":
        raise ConflictError("只有待审状态的变更可以修订")
    if change.operation not in {"create", "update"}:
        raise ValidationError("删除提案没有可修订的待采用内容")
    if change.target_type not in {"note", "note_category", "character", "world_entry"}:
        raise ValidationError("不支持的待审变更目标")
    target_type = cast(apply_service.PendingTargetType, change.target_type)
    allowed = (
        {"title"}
        if target_type == "note_category"
        else {"title", "body", "edits", "agent_visibility"}
    )
    if target_type == "world_entry":
        allowed.add("section")
    if not patch or set(patch) - allowed:
        raise ValidationError("修订只能包含该资料可编辑的字段，且不能为空")
    if not isinstance(change.after, dict):
        raise ValidationError("待采用内容无效")
    after = apply_service._prepare_after(target_type, patch, change.after)
    after = apply_service._validate_stored_after(
        target_type, change.operation, after, change.before
    )
    assert after is not None
    # SQLite stores UTC without a timezone; normalize API/model timestamps first.
    expected = expected_updated_at
    if expected.tzinfo is not None:
        expected = expected.astimezone(UTC).replace(tzinfo=None)
    if not await pending_project_change_repo.revise_if_current(session, change, after, expected):
        raise ConflictError("待审提案已变化，请重新读取后再修订；本次修改未保存")
    return change
