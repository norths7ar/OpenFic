"""Read and restore document recovery records in the caller's transaction."""

import json
from datetime import UTC, datetime
from typing import Any, Literal, cast

from sqlalchemy import delete, event, func, literal_column, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import QueryableAttribute, defer
from sqlmodel import col

from app.core.errors import ConflictError, NotFoundError
from app.storage.history_capture import with_history_source
from app.storage.models.chapter import Chapter
from app.storage.models.character import Character
from app.storage.models.document_history import DocumentHistory, DocumentTrash
from app.storage.models.note import Note
from app.storage.models.project import Project
from app.storage.models.project_folder import ProjectFolder
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry

DocumentKind = Literal["chapter", "world_entry", "character", "note", "outline"]
MODELS = {
    "chapter": Chapter,
    "world_entry": WorldInfoEntry,
    "character": Character,
    "note": Note,
    "outline": Note,
}
FOLDERS = {
    "chapter": "volume_id",
    "world_entry": "folder_id",
    "character": "folder_id",
    "note": "category_id",
    "outline": "category_id",
}
SCOPES = {
    "chapter": "writing",
    "world_entry": "world",
    "character": "character",
    "note": "note",
    "outline": "outline",
}


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def get_document(session, project_id, kind, document_id):
    model = MODELS[kind]
    document = await session.get(model, document_id)
    if document is None:
        raise NotFoundError("文档不存在")
    if kind == "world_entry":
        world = await session.get(WorldInfo, document.world_info_id)
        owner = world.project_id if world is not None else None
    else:
        owner = document.project_id
    if owner != project_id or (kind in ("note", "outline") and document.document_type != kind):
        raise NotFoundError("文档不存在")
    return document


async def _unlocked(session):
    from app.agent_runtime.session_activity import has_active_agent_sessions

    if await has_active_agent_sessions(session):
        raise ConflictError("Agent 正在运行，请停止后再恢复或永久删除")


async def history_list(session, project_id, kind, document_id, *, metadata_only=False):
    document = await get_document(session, project_id, kind, document_id)
    statement = select(DocumentHistory)
    if metadata_only:
        statement = statement.options(defer(cast(QueryableAttribute[Any], DocumentHistory.content)))
    items = (
        (
            await session.execute(
                statement.where(
                    col(DocumentHistory.project_id) == project_id,
                    col(DocumentHistory.kind) == kind,
                    col(DocumentHistory.document_id) == document_id,
                ).order_by(col(DocumentHistory.created_at).desc(), literal_column("rowid").desc())
            )
        )
        .scalars()
        .all()
    )
    return items, utc(document.updated_at)


async def history_detail(session, project_id, kind, document_id, history_id):
    await get_document(session, project_id, kind, document_id)
    item = await session.get(DocumentHistory, history_id, populate_existing=True)
    if item is None or (item.project_id, item.kind, item.document_id) != (
        project_id,
        kind,
        document_id,
    ):
        raise NotFoundError("历史版本不存在")
    return item


@with_history_source("restore")
async def restore_history(session, project_id, kind, document_id, history_id, base_updated_at):
    await _unlocked(session)
    item = await history_detail(session, project_id, kind, document_id, history_id)
    model = MODELS[kind]
    document = await get_document(session, project_id, kind, document_id)
    # Acquire SQLite's writer lock and compare the editor's base atomically.
    guarded = await session.execute(
        update(model)
        .where(
            col(model.id) == document_id,
            col(model.updated_at) == utc(base_updated_at).replace(tzinfo=None),
        )
        .values(updated_at=col(model.updated_at))
        .returning(col(model.id))
    )
    if guarded.scalar_one_or_none() is None:
        raise ConflictError("文档已被修改，请刷新历史后重试")
    await session.refresh(document)
    from app.storage.services import (
        chapter_service,
        character_service,
        note_service,
        world_info_entry_service,
    )

    if kind == "chapter":
        await chapter_service.update_chapter(
            session, document_id, title=item.title, content=item.content
        )
    elif kind == "character":
        await character_service.update_character(
            session, document_id, name=item.title, description=item.content
        )
    elif kind == "world_entry":
        await world_info_entry_service.update_entry(
            session,
            document_id,
            name=item.title,
            content=item.content,
            token_count=world_info_entry_service.calculate_token_count(item.content),
        )
    else:
        await note_service.update_note(session, document_id, title=item.title, content=item.content)
    await session.flush()


async def trash_list(session, project_id):
    if await session.get(Project, project_id) is None:
        raise NotFoundError("项目不存在")
    return (
        (
            await session.execute(
                select(DocumentTrash)
                .where(col(DocumentTrash.project_id) == project_id)
                .order_by(col(DocumentTrash.deleted_at).desc())
            )
        )
        .scalars()
        .all()
    )


async def _trash(session, project_id, trash_id):
    item = await session.get(DocumentTrash, trash_id)
    if item is None or item.project_id != project_id:
        raise NotFoundError("回收站文档不存在")
    return item


async def restore_trash(session: AsyncSession, project_id: str, trash_id: str):
    await _unlocked(session)
    # Serialize competing restores before reading occupancy or allocating order.
    await session.execute(
        update(Project)
        .where(col(Project.id) == project_id)
        .values(updated_at=col(Project.updated_at))
    )
    item = await _trash(session, project_id, trash_id)
    model = cast(Any, MODELS[item.kind])
    if await session.get(model, item.document_id) is not None:
        raise ConflictError("同 ID 文档已存在，不能覆盖")
    payload = json.loads(item.payload)
    folder_key = FOLDERS[item.kind]
    folder = (
        await session.get(ProjectFolder, payload[folder_key]) if payload.get(folder_key) else None
    )
    if folder is None or folder.project_id != project_id or folder.scope != SCOPES[item.kind]:
        payload[folder_key] = None
    if item.kind == "world_entry":
        world = await session.get(WorldInfo, payload["world_info_id"])
        if world is None or world.project_id != project_id:
            world = (
                await session.execute(
                    select(WorldInfo).where(col(WorldInfo.project_id) == project_id)
                )
            ).scalar_one_or_none()
            if world is None:
                world = WorldInfo(project_id=project_id, name="世界书")
                session.add(world)
                await session.flush()
            payload["world_info_id"] = world.id
        owner = col(WorldInfoEntry.world_info_id) == payload["world_info_id"]
        uid_occupied = (
            await session.execute(
                select(col(model.id))
                .where(owner, col(WorldInfoEntry.uid) == payload["uid"])
                .limit(1)
            )
        ).scalar_one_or_none()
        if uid_occupied is not None:
            payload["uid"] = (
                await session.execute(select(func.max(col(WorldInfoEntry.uid))).where(owner))
            ).scalar_one() + 1
    else:
        owner = col(model.project_id) == project_id
    if item.kind in ("world_entry", "character"):
        duplicate = (
            await session.execute(
                select(col(model.id)).where(owner, col(model.name) == payload["name"]).limit(1)
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise ConflictError("已存在同名文档，请先重命名现有文档")
    maximum = (
        await session.execute(
            select(func.max(col(model.order))).where(
                owner, getattr(model, folder_key) == payload[folder_key]
            )
        )
    ).scalar_one_or_none()
    payload["order"] = (maximum or 0) + 1
    payload["updated_at"] = datetime.now(UTC)
    document = model.model_validate(payload)
    await session.delete(item)
    await session.flush()
    session.add(document)
    await session.flush()
    if item.kind == "chapter":
        from app.storage.services.chapter_service import _update_volume_stats
        from app.storage.services.version_control_service import refresh_project_stats

        await _update_volume_stats(session, payload["volume_id"])
        await refresh_project_stats(session, project_id)
    return document.id, item.kind


async def delete_trash(session, project_id, trash_id):
    await _unlocked(session)
    await session.execute(
        update(Project)
        .where(col(Project.id) == project_id)
        .values(updated_at=col(Project.updated_at))
    )
    item = await _trash(session, project_id, trash_id)
    # An import / revision rollback may already have recreated this ID.
    # Never erase the history or image belonging to an active document.
    active = await session.get(MODELS[item.kind], item.document_id)
    await session.delete(item)
    await session.flush()
    remaining = (
        await session.execute(
            select(col(DocumentTrash.id))
            .where(
                col(DocumentTrash.document_id) == item.document_id,
                col(DocumentTrash.kind) == item.kind,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if active is None and remaining is None:
        await session.execute(
            delete(DocumentHistory).where(
                col(DocumentHistory.project_id) == project_id,
                col(DocumentHistory.kind) == item.kind,
                col(DocumentHistory.document_id) == item.document_id,
            )
        )
        if item.kind == "character":
            path = json.loads(item.payload).get("image_path")
            if path:
                other_image = (
                    await session.execute(
                        select(col(Character.id)).where(col(Character.image_path) == path).limit(1)
                    )
                ).scalar_one_or_none()
                other_trash = (
                    await session.execute(
                        select(col(DocumentTrash.id))
                        .where(
                            func.json_extract(col(DocumentTrash.payload), "$.image_path") == path
                        )
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if other_image is None and other_trash is None:
                    schedule_image_cleanup(session, [path])
    return item


def schedule_image_cleanup(session, paths):
    """Only remove recovery-owned files after a successful database commit."""
    sync = session.sync_session
    sync.info.setdefault("history_image_cleanup", set()).update(paths)
    if sync.info.get("history_image_cleanup_listeners"):
        return
    sync.info["history_image_cleanup_listeners"] = True

    @event.listens_for(sync, "after_commit")
    def cleanup(committed):
        if committed.in_nested_transaction():
            return
        from loguru import logger

        from app.core.storage import delete_character_image

        for path in committed.info.pop("history_image_cleanup", set()):
            try:
                delete_character_image(path)
            except OSError:
                logger.exception("Failed to remove a permanently deleted character image")

    @event.listens_for(sync, "after_rollback")
    def discard(rolled_back):
        rolled_back.info.pop("history_image_cleanup", None)


async def schedule_project_image_cleanup(session, project_id):
    active = (
        (
            await session.execute(
                select(col(Character.image_path)).where(
                    col(Character.project_id) == project_id, col(Character.image_path).is_not(None)
                )
            )
        )
        .scalars()
        .all()
    )
    trashed = (
        (
            await session.execute(
                select(col(DocumentTrash.payload)).where(
                    col(DocumentTrash.project_id) == project_id,
                    col(DocumentTrash.kind) == "character",
                )
            )
        )
        .scalars()
        .all()
    )
    paths = set(active)
    paths.update(path for payload in trashed if (path := json.loads(payload).get("image_path")))
    schedule_image_cleanup(session, paths)
