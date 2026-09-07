"""Compatibility queries for note-category endpoints, backed only by project folders."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.storage.models.project_folder import ProjectFolder
from app.storage.repos import project_folder_repo


async def create(session: AsyncSession, category: ProjectFolder) -> ProjectFolder:
    return await project_folder_repo.save(session, category)


async def get_by_id(session: AsyncSession, category_id: str) -> ProjectFolder | None:
    folder = await project_folder_repo.get_by_id(session, category_id)
    return folder if folder is not None and folder.scope in {"note", "outline"} else None


async def get_max_order(
    session: AsyncSession, project_id: str, parent_id: str | None, document_type: str = "note"
) -> int:
    if parent_id is not None:
        raise ValueError("文件夹只支持一层")
    return await project_folder_repo.get_max_order(session, project_id, document_type)


async def list_by_project(
    session: AsyncSession, project_id: str, document_type: str | None = None
) -> list[ProjectFolder]:
    scopes = [document_type] if document_type is not None else ["note", "outline"]
    result = await session.execute(
        select(ProjectFolder)
        .where(col(ProjectFolder.project_id) == project_id, col(ProjectFolder.scope).in_(scopes))
        .order_by(col(ProjectFolder.order), col(ProjectFolder.id))
    )
    return list(result.scalars().all())


async def get_by_parent(session: AsyncSession, parent_id: str | None) -> list[ProjectFolder]:
    if parent_id is not None:
        return []
    result = await session.execute(
        select(ProjectFolder)
        .where(col(ProjectFolder.scope).in_(["note", "outline"]))
        .order_by(col(ProjectFolder.order), col(ProjectFolder.id))
    )
    return list(result.scalars().all())


async def update_category(session: AsyncSession, category: ProjectFolder) -> ProjectFolder:
    return await project_folder_repo.save(session, category)


async def delete(session: AsyncSession, category: ProjectFolder) -> None:
    await project_folder_repo.delete(session, category)


async def search_mention_candidates(
    session: AsyncSession, project_id: str, query: str, *, limit: int
) -> list[ProjectFolder]:
    if not query.strip():
        return []
    result = await session.execute(
        select(ProjectFolder)
        .where(
            col(ProjectFolder.project_id) == project_id,
            col(ProjectFolder.scope).in_(["note", "outline"]),
            func.lower(col(ProjectFolder.title)).contains(query.strip().lower()),
        )
        .order_by(col(ProjectFolder.order), col(ProjectFolder.id))
        .limit(limit)
    )
    return list(result.scalars().all())
