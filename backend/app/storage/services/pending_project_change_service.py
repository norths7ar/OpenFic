"""待审项目变更业务逻辑层。"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.storage.models.pending_project_change import PendingProjectChange
from app.storage.repos import pending_project_change_repo, project_repo


async def _ensure_project_exists(session: AsyncSession, project_id: str) -> None:
    if await project_repo.get_by_id(session, project_id) is None:
        raise NotFoundError(f"项目不存在: {project_id}")


async def create_pending_change(
    session: AsyncSession,
    *,
    project_id: str,
    target_type: str,
    target_id: str | None,
    operation: str,
    base_hash: str | None,
    before: Any,
    after: Any,
    source_task_id: str | None,
    source_message_id: str | None,
    model_id: str | None,
) -> PendingProjectChange:
    """创建一条绑定项目的待审变更。"""
    await _ensure_project_exists(session, project_id)
    change = PendingProjectChange(
        project_id=project_id,
        target_type=target_type,
        target_id=target_id,
        operation=operation,
        base_hash=base_hash,
        before=before,
        after=after,
        source_task_id=source_task_id,
        source_message_id=source_message_id,
        model_id=model_id,
    )
    return await pending_project_change_repo.create(session, change)


async def list_pending_changes(
    session: AsyncSession,
    project_id: str,
    status: str | None = None,
) -> list[PendingProjectChange]:
    """获取项目下的待审变更。"""
    await _ensure_project_exists(session, project_id)
    return await pending_project_change_repo.list_by_project(
        session, project_id, status
    )


async def count_pending_changes(
    session: AsyncSession,
    project_id: str,
    status: str,
) -> int:
    """统计项目下指定状态的待审变更。"""
    await _ensure_project_exists(session, project_id)
    return await pending_project_change_repo.count_by_project(
        session, project_id, status
    )


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
) -> PendingProjectChange:
    """拒绝待审变更；重复拒绝保持幂等。"""
    change = await get_pending_change(session, project_id, change_id)
    if change.status == "rejected":
        return change
    change.status = "rejected"
    change.updated_at = datetime.now(UTC)
    return await pending_project_change_repo.update(session, change)
