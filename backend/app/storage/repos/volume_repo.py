"""
ProjectFolder Repository - 卷数据访问层。
"""

from sqlalchemy import case, func, select, update
from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.storage.models.project_folder import ProjectFolder


async def create(session: AsyncSession, volume: ProjectFolder) -> ProjectFolder:
    """创建卷。"""
    session.add(volume)
    await session.flush()
    await session.refresh(volume)
    return volume


async def get_by_id(session: AsyncSession, volume_id: str) -> ProjectFolder | None:
    """根据 ID 获取卷。"""
    result = await session.execute(
        select(ProjectFolder).where(
            col(ProjectFolder.id) == volume_id, col(ProjectFolder.scope) == "writing"
        )
    )
    return result.scalar_one_or_none()


async def list_by_project(session: AsyncSession, project_id: str) -> list[ProjectFolder]:
    """获取项目下的卷列表。"""
    result = await session.execute(
        select(ProjectFolder)
        .where(col(ProjectFolder.project_id) == project_id, col(ProjectFolder.scope) == "writing")
        .order_by(col(ProjectFolder.order).asc())
    )
    return list(result.scalars().all())


async def search_by_project(
    session: AsyncSession,
    project_id: str,
    query: str,
    *,
    limit: int,
) -> list[ProjectFolder]:
    """按标题搜索项目下的卷。"""
    normalized_query = query.strip().lower()
    if not normalized_query:
        return []

    title_expr = func.lower(func.coalesce(col(ProjectFolder.title), ""))
    match_rank = case(
        (title_expr == normalized_query, 0),
        (title_expr.like(f"{normalized_query}%"), 1),
        else_=2,
    )

    result = await session.execute(
        select(ProjectFolder)
        .where(
            col(ProjectFolder.project_id) == project_id,
            col(ProjectFolder.scope) == "writing",
            title_expr.contains(normalized_query),
        )
        .order_by(match_rank.asc(), col(ProjectFolder.order).asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def count_by_project(session: AsyncSession, project_id: str) -> int:
    """获取项目下卷数。"""
    result = await session.execute(
        select(func.count(col(ProjectFolder.id))).where(
            col(ProjectFolder.project_id) == project_id, col(ProjectFolder.scope) == "writing"
        )
    )
    return result.scalar_one()


async def get_max_order(session: AsyncSession, project_id: str) -> int:
    """获取项目下最大卷序号。"""
    result = await session.execute(
        select(func.max(col(ProjectFolder.order))).where(
            col(ProjectFolder.project_id) == project_id, col(ProjectFolder.scope) == "writing"
        )
    )
    max_order = result.scalar_one_or_none()
    return max_order if max_order is not None else 0


async def update_volume(session: AsyncSession, volume: ProjectFolder) -> ProjectFolder:
    """更新卷。"""
    session.add(volume)
    await session.flush()
    await session.refresh(volume)
    return volume


async def delete(session: AsyncSession, volume: ProjectFolder) -> None:
    """删除卷。"""
    await session.delete(volume)
    await session.flush()


async def delete_by_project(session: AsyncSession, project_id: str) -> None:
    """删除项目下所有卷。"""
    await session.execute(
        sql_delete(ProjectFolder).where(
            col(ProjectFolder.project_id) == project_id, col(ProjectFolder.scope) == "writing"
        )
    )
    await session.flush()


async def shift_orders(
    session: AsyncSession,
    project_id: str,
    start_order: int,
    end_order: int,
    delta: int,
) -> None:
    """批量调整项目内卷序号。"""
    await session.execute(
        update(ProjectFolder)
        .where(
            col(ProjectFolder.project_id) == project_id,
            col(ProjectFolder.scope) == "writing",
            col(ProjectFolder.order) >= start_order,
            col(ProjectFolder.order) <= end_order,
        )
        .values(order=col(ProjectFolder.order) + delta)
    )
    await session.flush()
