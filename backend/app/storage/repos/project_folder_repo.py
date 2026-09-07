"""Persistence helpers for project folders."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.storage.models.project_folder import ProjectFolder


async def get_by_id(session: AsyncSession, folder_id: str) -> ProjectFolder | None:
    return await session.get(ProjectFolder, folder_id)


async def list_by_project_scope(
    session: AsyncSession,
    project_id: str,
    scope: str,
) -> list[ProjectFolder]:
    result = await session.execute(
        select(ProjectFolder)
        .where(
            col(ProjectFolder.project_id) == project_id,
            col(ProjectFolder.scope) == scope,
        )
        .order_by(col(ProjectFolder.order), col(ProjectFolder.id))
    )
    return list(result.scalars().all())


async def get_max_order(session: AsyncSession, project_id: str, scope: str) -> int:
    result = await session.execute(
        select(func.max(col(ProjectFolder.order))).where(
            col(ProjectFolder.project_id) == project_id,
            col(ProjectFolder.scope) == scope,
        )
    )
    return int(result.scalar_one_or_none() or 0)


async def save(session: AsyncSession, folder: ProjectFolder) -> ProjectFolder:
    session.add(folder)
    await session.flush()
    await session.refresh(folder)
    return folder


async def delete(session: AsyncSession, folder: ProjectFolder) -> None:
    await session.delete(folder)
    await session.flush()
