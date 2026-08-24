"""待审项目变更数据访问层。"""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.storage.models.pending_project_change import PendingProjectChange


async def create(
    session: AsyncSession,
    change: PendingProjectChange,
) -> PendingProjectChange:
    """创建待审变更。"""
    session.add(change)
    await session.flush()
    await session.refresh(change)
    return change


async def get_by_id(
    session: AsyncSession,
    project_id: str,
    change_id: str,
) -> PendingProjectChange | None:
    """按项目范围获取待审变更。"""
    result = await session.execute(
        select(PendingProjectChange).where(
            col(PendingProjectChange.project_id) == project_id,
            col(PendingProjectChange.id) == change_id,
        )
    )
    return result.scalar_one_or_none()


async def list_by_project(
    session: AsyncSession,
    project_id: str,
    status: str | None = None,
) -> list[PendingProjectChange]:
    """获取项目下的待审变更，最新创建的排在前面。"""
    query = (
        select(PendingProjectChange)
        .where(col(PendingProjectChange.project_id) == project_id)
        .order_by(
            col(PendingProjectChange.created_at).desc(),
            col(PendingProjectChange.id).desc(),
        )
    )
    if status is not None:
        query = query.where(col(PendingProjectChange.status) == status)

    result = await session.execute(query)
    return list(result.scalars().all())


async def count_by_project(
    session: AsyncSession,
    project_id: str,
    status: str,
) -> int:
    """统计项目下指定状态的待审变更。"""
    result = await session.execute(
        select(func.count(col(PendingProjectChange.id))).where(
            col(PendingProjectChange.project_id) == project_id,
            col(PendingProjectChange.status) == status,
        )
    )
    return result.scalar_one()


async def update(
    session: AsyncSession,
    change: PendingProjectChange,
) -> PendingProjectChange:
    """更新待审变更。"""
    session.add(change)
    await session.flush()
    await session.refresh(change)
    return change


async def delete_by_project(session: AsyncSession, project_id: str) -> None:
    """删除项目下的所有待审变更。"""
    await session.execute(
        delete(PendingProjectChange).where(
            col(PendingProjectChange.project_id) == project_id
        )
    )
    await session.flush()
