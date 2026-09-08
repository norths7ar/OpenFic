"""Business rules for shared single-level project folders."""

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.errors import NotFoundError
from app.storage.models.chapter import Chapter
from app.storage.models.chapter_summary import ChapterSummary
from app.storage.models.character import Character
from app.storage.models.note import Note
from app.storage.models.project_folder import ProjectFolder
from app.storage.models.task import Task
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry
from app.storage.repos import project_folder_repo, project_repo, world_info_repo

UNSET = object()

ProjectFolderScope = Literal["writing", "discussion", "world", "character", "outline", "note"]


async def list_folders(
    session: AsyncSession,
    project_id: str,
    scope: ProjectFolderScope,
) -> list[ProjectFolder]:
    if await project_repo.get_by_id(session, project_id) is None:
        raise NotFoundError(f"项目不存在: {project_id}")
    return await project_folder_repo.list_by_project_scope(session, project_id, scope)


async def create_folder(
    session: AsyncSession,
    project_id: str,
    scope: ProjectFolderScope,
    title: str,
    description: str | None = None,
) -> ProjectFolder:
    if await project_repo.get_by_id(session, project_id) is None:
        raise NotFoundError(f"项目不存在: {project_id}")
    return await project_folder_repo.save(
        session,
        ProjectFolder(
            project_id=project_id,
            scope=scope,
            title=title,
            description=description,
            order=await project_folder_repo.get_max_order(session, project_id, scope) + 1,
        ),
    )


async def update_folder(
    session: AsyncSession,
    folder_id: str,
    title: str | None = None,
    description: str | None | object = UNSET,
) -> ProjectFolder:
    folder = await project_folder_repo.get_by_id(session, folder_id)
    if folder is None:
        raise NotFoundError(f"文件夹不存在: {folder_id}")
    if title is not None:
        folder.title = title
    if description is not UNSET:
        folder.description = description if isinstance(description, str) else None
    folder.updated_at = datetime.now(UTC)
    return await project_folder_repo.save(session, folder)


async def require_folder(
    session: AsyncSession,
    folder_id: str | None,
    *,
    project_id: str,
    scope: ProjectFolderScope,
) -> ProjectFolder | None:
    if folder_id is None:
        return None
    folder = await project_folder_repo.get_by_id(session, folder_id)
    if folder is None or folder.project_id != project_id or folder.scope != scope:
        raise ValueError("文件夹不存在或不属于当前页面")
    return folder


async def delete_folder(session: AsyncSession, folder_id: str) -> None:
    folder = await project_folder_repo.get_by_id(session, folder_id)
    if folder is None:
        raise NotFoundError(f"文件夹不存在: {folder_id}")
    # Keep the query/model pairing explicit. These scopes use distinct foreign
    # keys and ownership paths, so a dynamic union would both hide mistakes and
    # let static typing accept invalid model attributes.
    if folder.scope == "discussion":
        children = list(
            (
                await session.execute(
                    select(Task)
                    .where(
                        col(Task.project_id) == folder.project_id,
                        col(Task.folder_id) == folder.id,
                    )
                    .order_by(col(Task.created_at), col(Task.id))
                )
            ).scalars()
        )
        for item in children:
            item.folder_id = None
            session.add(item)
    elif folder.scope == "world":
        project_world_ids = select(col(WorldInfo.id)).where(
            col(WorldInfo.project_id) == folder.project_id
        )
        roots = list(
            (
                await session.execute(
                    select(WorldInfoEntry)
                    .where(
                        col(WorldInfoEntry.world_info_id).in_(project_world_ids),
                        col(WorldInfoEntry.folder_id).is_(None),
                    )
                    .order_by(col(WorldInfoEntry.order), col(WorldInfoEntry.id))
                )
            ).scalars()
        )
        children = list(
            (
                await session.execute(
                    select(WorldInfoEntry)
                    .where(
                        col(WorldInfoEntry.world_info_id).in_(project_world_ids),
                        col(WorldInfoEntry.folder_id) == folder.id,
                    )
                    .order_by(col(WorldInfoEntry.order), col(WorldInfoEntry.id))
                )
            ).scalars()
        )
        next_order = max((item.order for item in roots), default=0) + 1
        for offset, item in enumerate(children):
            item.folder_id = None
            item.order = next_order + offset
            session.add(item)
    elif folder.scope == "character":
        roots = list(
            (
                await session.execute(
                    select(Character)
                    .where(
                        col(Character.project_id) == folder.project_id,
                        col(Character.folder_id).is_(None),
                    )
                    .order_by(col(Character.order), col(Character.id))
                )
            ).scalars()
        )
        children = list(
            (
                await session.execute(
                    select(Character)
                    .where(
                        col(Character.project_id) == folder.project_id,
                        col(Character.folder_id) == folder.id,
                    )
                    .order_by(col(Character.order), col(Character.id))
                )
            ).scalars()
        )
        next_order = max((item.order for item in roots), default=0) + 1
        for offset, item in enumerate(children):
            item.folder_id = None
            item.order = next_order + offset
            session.add(item)
    elif folder.scope == "writing":
        roots = list(
            (
                await session.execute(
                    select(Chapter)
                    .where(
                        col(Chapter.project_id) == folder.project_id,
                        col(Chapter.volume_id).is_(None),
                    )
                    .order_by(col(Chapter.order), col(Chapter.id))
                )
            ).scalars()
        )
        children = list(
            (
                await session.execute(
                    select(Chapter)
                    .where(
                        col(Chapter.project_id) == folder.project_id,
                        col(Chapter.volume_id) == folder.id,
                    )
                    .order_by(col(Chapter.order), col(Chapter.id))
                )
            ).scalars()
        )
        next_order = max((item.order for item in roots), default=0) + 1
        for offset, item in enumerate(children):
            item.volume_id = None
            item.order = next_order + offset
            session.add(item)
    elif folder.scope in {"note", "outline"}:
        roots = list(
            (
                await session.execute(
                    select(Note)
                    .where(
                        col(Note.project_id) == folder.project_id,
                        col(Note.document_type) == folder.scope,
                        col(Note.category_id).is_(None),
                    )
                    .order_by(col(Note.order), col(Note.id))
                )
            ).scalars()
        )
        children = list(
            (
                await session.execute(
                    select(Note)
                    .where(
                        col(Note.project_id) == folder.project_id,
                        col(Note.document_type) == folder.scope,
                        col(Note.category_id) == folder.id,
                    )
                    .order_by(col(Note.order), col(Note.id))
                )
            ).scalars()
        )
        next_order = max((item.order for item in roots), default=0) + 1
        for offset, item in enumerate(children):
            item.category_id = None
            item.order = next_order + offset
            session.add(item)
    else:
        raise ValueError("不支持的文件夹页面")
    if folder.scope == "writing":
        await session.execute(
            update(ChapterSummary)
            .where(col(ChapterSummary.volume_id) == folder.id)
            .values(volume_id=None)
        )
    await session.flush()
    await project_folder_repo.delete(session, folder)


async def move_item(
    session: AsyncSession,
    project_id: str,
    scope: ProjectFolderScope,
    item_id: str,
    folder_id: str | None,
) -> None:
    await require_folder(session, folder_id, project_id=project_id, scope=scope)
    if scope in {"note", "outline"}:
        from app.storage.services import note_service

        note = await session.get(Note, item_id)
        if note is None or note.project_id != project_id or note.document_type != scope:
            raise ValueError("条目不属于当前页面")
        await note_service.move_item(session, "note", item_id, folder_id)
        return
    if scope == "writing":
        from app.storage.services import chapter_service

        chapter = await session.get(Chapter, item_id)
        if chapter is None or chapter.project_id != project_id:
            raise ValueError("条目不属于当前页面")
        await chapter_service.move_chapter_to_volume(session, item_id, folder_id)
        return
    if scope == "world":
        item = await session.get(WorldInfoEntry, item_id)
        if item is None:
            raise NotFoundError(f"条目不存在: {item_id}")
        world = await world_info_repo.get_by_id(session, item.world_info_id)
        item_project_id = world.project_id if world is not None else None
    elif scope == "discussion":
        item = await session.get(Task, item_id)
        if item is None:
            raise NotFoundError(f"条目不存在: {item_id}")
        item_project_id = item.project_id
    else:
        item = await session.get(Character, item_id)
        if item is None:
            raise NotFoundError(f"条目不存在: {item_id}")
        item_project_id = item.project_id
    if item_project_id != project_id:
        raise ValueError("条目不属于当前项目")
    if item.folder_id == folder_id:
        return
    item.folder_id = folder_id
    session.add(item)
    await session.flush()


async def reorder_folders(
    session: AsyncSession,
    project_id: str,
    scope: ProjectFolderScope,
    ordered_ids: list[str],
) -> int:
    folders = await project_folder_repo.list_by_project_scope(session, project_id, scope)
    if len(ordered_ids) != len(set(ordered_ids)) or set(ordered_ids) != {
        folder.id for folder in folders
    }:
        raise ValueError("ordered_ids 必须完整匹配当前页面的文件夹")
    by_id = {folder.id: folder for folder in folders}
    now = datetime.now(UTC)
    for order, folder_id in enumerate(ordered_ids, start=1):
        folder = by_id[folder_id]
        folder.order = order
        folder.updated_at = now
        session.add(folder)
    await session.flush()
    return len(ordered_ids)
