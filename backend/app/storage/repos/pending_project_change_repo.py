"""待审项目变更数据访问层。"""

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import delete, func, select
from sqlalchemy import update as sql_update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.storage.models.pending_project_change import (
    PendingProjectChange,
    PendingProjectChangeRevision,
)
from app.storage.models.project import Project


async def lock_project(session: AsyncSession, project_id: str) -> None:
    """Acquire SQLite's transaction write lock before reading duplicate candidates.

    A unique index would reject pre-existing duplicate proposals. A no-op write
    instead serializes the check/insert with no change to project metadata.
    """
    await session.execute(
        sql_update(Project)
        .where(col(Project.id) == project_id)
        .values(id=col(Project.id))
        .execution_options(synchronize_session=False)
    )


async def add_revision(
    session: AsyncSession, revision: PendingProjectChangeRevision
) -> PendingProjectChangeRevision:
    session.add(revision)
    await session.flush()
    return revision


async def list_revisions(
    session: AsyncSession, change_id: str
) -> list[PendingProjectChangeRevision]:
    result = await session.execute(
        select(PendingProjectChangeRevision)
        .where(col(PendingProjectChangeRevision.change_id) == change_id)
        .order_by(
            col(PendingProjectChangeRevision.created_at).desc(),
            col(PendingProjectChangeRevision.id).desc(),
        )
    )
    return list(result.scalars().all())


async def get_revision(
    session: AsyncSession, change_id: str, revision_id: str
) -> PendingProjectChangeRevision | None:
    result = await session.execute(
        select(PendingProjectChangeRevision).where(
            col(PendingProjectChangeRevision.change_id) == change_id,
            col(PendingProjectChangeRevision.id) == revision_id,
        )
    )
    return result.scalar_one_or_none()


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
        select(PendingProjectChange)
        .where(
            col(PendingProjectChange.project_id) == project_id,
            col(PendingProjectChange.id) == change_id,
        )
        .execution_options(populate_existing=True)
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


async def claim_for_apply(
    session: AsyncSession,
    project_id: str,
    change_id: str,
    expected_updated_at: datetime | None = None,
) -> bool:
    """原子地领取一条待审变更。"""
    version_filter = (
        [col(PendingProjectChange.updated_at) == expected_updated_at]
        if expected_updated_at is not None
        else []
    )
    result = cast(
        CursorResult[Any],
        await session.execute(
            sql_update(PendingProjectChange)
            .where(
                col(PendingProjectChange.project_id) == project_id,
                col(PendingProjectChange.id) == change_id,
                col(PendingProjectChange.status) == "pending",
                *version_filter,
            )
            .values(status="applying", updated_at=datetime.now(UTC))
            .execution_options(synchronize_session=False)
        ),
    )
    await session.flush()
    return result.rowcount == 1


async def revise_if_current(
    session: AsyncSession,
    change: PendingProjectChange,
    after: dict[str, Any],
    expected_updated_at: datetime,
    revision_id: str,
) -> bool:
    """Save a draft only if the caller still owns the version it read."""
    result = cast(
        CursorResult[Any],
        await session.execute(
            sql_update(PendingProjectChange)
            .where(
                col(PendingProjectChange.project_id) == change.project_id,
                col(PendingProjectChange.id) == change.id,
                col(PendingProjectChange.status) == "pending",
                col(PendingProjectChange.updated_at) == expected_updated_at,
            )
            .values(after=after, current_revision_id=revision_id, updated_at=datetime.now(UTC))
            .execution_options(synchronize_session=False)
        ),
    )
    await session.flush()
    await session.refresh(change)
    return result.rowcount == 1


async def reject_if_current(
    session: AsyncSession, change: PendingProjectChange, expected_updated_at: datetime
) -> bool:
    result = cast(
        CursorResult[Any],
        await session.execute(
            sql_update(PendingProjectChange)
            .where(
                col(PendingProjectChange.project_id) == change.project_id,
                col(PendingProjectChange.id) == change.id,
                col(PendingProjectChange.status) == "pending",
                col(PendingProjectChange.updated_at) == expected_updated_at,
            )
            .values(status="rejected", updated_at=datetime.now(UTC))
            .execution_options(synchronize_session=False)
        ),
    )
    await session.flush()
    await session.refresh(change)
    return result.rowcount == 1


async def delete_by_project(session: AsyncSession, project_id: str) -> None:
    """删除项目下的所有待审变更。"""
    await session.execute(
        delete(PendingProjectChangeRevision).where(
            col(PendingProjectChangeRevision.change_id).in_(
                select(col(PendingProjectChange.id)).where(
                    col(PendingProjectChange.project_id) == project_id
                )
            )
        )
    )
    await session.execute(
        delete(PendingProjectChange).where(col(PendingProjectChange.project_id) == project_id)
    )
    await session.flush()
