"""待审项目变更业务逻辑层。"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.storage.models.pending_project_change import (
    PendingProjectChange,
    PendingProjectChangeRevision,
)
from app.storage.repos import pending_project_change_repo, project_repo


class PendingChangeDuplicateError(ConflictError):
    def __init__(self, candidate_ids: list[str]) -> None:
        super().__init__(
            "同一目标已有待审提案，请读取并修订已有提案；多个候选时须明确选择，不得自动选择"
        )
        self.candidate_ids = sorted(candidate_ids)

    def detail(self) -> dict[str, Any]:
        return {
            "code": "pending_change_duplicate",
            "message": str(self),
            "candidate_ids": self.candidate_ids,
            "action": "revise_pending_project_change",
        }


def _same_target(change: PendingProjectChange, target_type: str, target_id: str | None) -> bool:
    return (
        target_id is not None
        and change.target_type == target_type
        and change.target_id == target_id
    )


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
    source: str = "manual",
) -> PendingProjectChange:
    """创建一条绑定项目、由服务端捕获基础快照的待审变更。"""
    await pending_project_change_repo.lock_project(session, project_id)
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
    # Check identity before interpreting edits: a caller may have quoted text
    # from the pending draft rather than from the canonical material.
    if target_id is not None:
        candidates = await pending_project_change_repo.list_by_project(session, project_id)
        duplicate_ids = [
            candidate.id
            for candidate in candidates
            if candidate.status in {"pending", "applying"}
            and _same_target(candidate, target_type, target_id)
        ]
        if duplicate_ids:
            raise PendingChangeDuplicateError(duplicate_ids)
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
    if change_id is not None:
        change.id = change_id
    try:
        async with session.begin_nested():
            await pending_project_change_repo.create(session, change)
            revision = await pending_project_change_repo.add_revision(
                session,
                PendingProjectChangeRevision(
                    change_id=change.id,
                    after=change.after,
                    source=source,
                    source_task_id=source_task_id,
                    source_message_id=source_message_id,
                    model_id=model_id,
                ),
            )
            change.current_revision_id = revision.id
            return await pending_project_change_repo.update(session, change)
    except IntegrityError:
        if change_id is None:
            raise
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


async def list_revisions(
    session: AsyncSession, project_id: str, change_id: str
) -> list[PendingProjectChangeRevision]:
    await get_pending_change(session, project_id, change_id)
    return await pending_project_change_repo.list_revisions(session, change_id)


async def get_revision(
    session: AsyncSession, project_id: str, change_id: str, revision_id: str
) -> PendingProjectChangeRevision:
    await get_pending_change(session, project_id, change_id)
    revision = await pending_project_change_repo.get_revision(session, change_id, revision_id)
    if revision is None:
        raise NotFoundError(f"提案修订版本不存在: {revision_id}")
    return revision


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
    source: str = "manual",
    source_task_id: str | None = None,
    source_message_id: str | None = None,
    model_id: str | None = None,
) -> PendingProjectChange:
    """Revise the proposed result without changing its authoritative base."""
    from app.storage.services import pending_project_change_apply_service as apply_service

    await pending_project_change_repo.lock_project(session, project_id)
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
    stored_timestamp = change.updated_at
    if stored_timestamp.tzinfo is not None:
        stored_timestamp = stored_timestamp.astimezone(UTC).replace(tzinfo=None)
    if expected != stored_timestamp:
        raise ConflictError("待审提案已变化，请重新读取后再修订；本次修改未保存")
    if after == change.after:
        return change
    async with session.begin_nested():
        revision = PendingProjectChangeRevision(
            change_id=change.id,
            after=after,
            source=source,
            source_task_id=source_task_id,
            source_message_id=source_message_id,
            model_id=model_id,
        )
        if not await pending_project_change_repo.revise_if_current(
            session, change, after, expected, revision.id
        ):
            raise ConflictError("待审提案已变化，请重新读取后再修订；本次修改未保存")
        await pending_project_change_repo.add_revision(session, revision)
    return change
