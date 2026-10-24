"""Project-scoped, metadata-only queries for mention browsing and search."""

from typing import Literal

from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col

from app.core.agent_visibility import values_for_scope
from app.core.knowledge_scope import KnowledgeScope
from app.storage.models.chapter import Chapter
from app.storage.models.character import Character
from app.storage.models.note import Note
from app.storage.models.project_folder import ProjectFolder
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry

MentionKind = Literal["volume", "chapter", "note", "note_category", "world_info_entry", "character"]
FOLDER_SCOPES: dict[MentionKind, tuple[str, ...]] = {
    "volume": (),
    "chapter": ("writing",),
    "note": ("note", "outline"),
    "note_category": (),
    "world_info_entry": ("world",),
    "character": ("character",),
}


async def list_folders(
    session: AsyncSession, project_id: str, kind: MentionKind | None
) -> list[ProjectFolder]:
    scopes = (
        FOLDER_SCOPES[kind]
        if kind is not None
        else ("writing", "note", "outline", "world", "character")
    )
    result = await session.execute(
        select(ProjectFolder)
        .where(
            col(ProjectFolder.project_id) == project_id,
            col(ProjectFolder.scope).in_(scopes),
        )
        .order_by(col(ProjectFolder.order), col(ProjectFolder.id))
    )
    return list(result.scalars().all())


async def search_by_kind(
    session: AsyncSession,
    project_id: str,
    kind: MentionKind,
    query: str,
    *,
    context_mode: KnowledgeScope,
    folder_id: str | None,
    limit: int,
) -> list[RowMapping]:
    """Fetch enough rows of one kind for the merged page, without loading bodies."""
    folder_name = col(ProjectFolder.title)
    folder_join = None
    extra_rank = None
    conditions: list[ColumnElement[bool]]
    if kind in {"volume", "note_category"}:
        model = ProjectFolder
        title = col(ProjectFolder.title)
        parent = literal(None)
        folder_name = literal(None)
        scopes = ("writing",) if kind == "volume" else ("note", "outline")
        conditions = [
            col(ProjectFolder.project_id) == project_id,
            col(ProjectFolder.scope).in_(scopes),
        ]
        matches = title.ilike(f"%{query}%")
        ordering = [col(ProjectFolder.order), col(ProjectFolder.id)]
    elif kind == "chapter":
        model = Chapter
        title = col(Chapter.title)
        parent = col(Chapter.volume_id)
        conditions = [col(Chapter.project_id) == project_id]
        folder_join = and_(
            col(ProjectFolder.id) == parent,
            col(ProjectFolder.project_id) == project_id,
            col(ProjectFolder.scope) == "writing",
        )
        matches = or_(title.ilike(f"%{query}%"), folder_name.ilike(f"%{query}%"))
        extra_rank = case(
            (func.lower(folder_name) == query, 3),
            (func.lower(folder_name).startswith(query), 4),
            else_=5,
        )
        ordering = [
            func.coalesce(col(ProjectFolder.order), -1),
            col(Chapter.order),
            col(Chapter.id),
        ]
    elif kind == "note":
        model = Note
        title = col(Note.title)
        parent = col(Note.category_id)
        conditions = [
            col(Note.project_id) == project_id,
            col(Note.agent_visibility).in_(values_for_scope(context_mode)),
        ]
        folder_join = and_(
            col(ProjectFolder.id) == parent,
            col(ProjectFolder.project_id) == project_id,
            col(ProjectFolder.scope) == col(Note.document_type),
        )
        matches = title.ilike(f"%{query}%")
        ordering = (
            [title, col(Note.order), col(Note.id)]
            if query
            else [col(Note.order), title, col(Note.id)]
        )
    elif kind == "world_info_entry":
        model = WorldInfoEntry
        title = col(WorldInfoEntry.name)
        parent = col(WorldInfoEntry.folder_id)
        conditions = [
            col(WorldInfoEntry.world_info_id).in_(
                select(col(WorldInfo.id)).where(col(WorldInfo.project_id) == project_id)
            ),
            col(WorldInfoEntry.agent_visibility).in_(values_for_scope(context_mode)),
        ]
        folder_join = and_(
            col(ProjectFolder.id) == parent,
            col(ProjectFolder.project_id) == project_id,
            col(ProjectFolder.scope) == "world",
        )
        matches = or_(title.ilike(f"%{query}%"), col(WorldInfoEntry.content).ilike(f"%{query}%"))
        ordering = [col(WorldInfoEntry.order), col(WorldInfoEntry.id)]
    else:
        model = Character
        title = col(Character.name)
        parent = col(Character.folder_id)
        conditions = [
            col(Character.project_id) == project_id,
            col(Character.agent_visibility).in_(values_for_scope(context_mode)),
        ]
        folder_join = and_(
            col(ProjectFolder.id) == parent,
            col(ProjectFolder.project_id) == project_id,
            col(ProjectFolder.scope) == "character",
        )
        matches = or_(title.ilike(f"%{query}%"), col(Character.description).ilike(f"%{query}%"))
        ordering = [col(Character.order), title, col(Character.id)]

    rank = (
        case(
            (func.lower(title) == query, 0),
            (func.lower(title).startswith(query), 1),
            (func.lower(title).contains(query), 2),
            else_=extra_rank if extra_rank is not None else 99,
        )
        if query
        else literal(0)
    )
    stmt = select(
        col(model.id).label("id"),
        title.label("title"),
        parent.label("folder_id"),
        folder_name.label("folder_name"),
        rank.label("rank"),
    ).select_from(model)
    if folder_join is not None:
        stmt = stmt.outerjoin(ProjectFolder, folder_join)
    if query:
        conditions.append(matches)
    if folder_id is not None:
        conditions.append(parent.is_(None) if folder_id == "root" else parent == folder_id)
        if folder_id != "root" and folder_join is not None:
            conditions.append(col(ProjectFolder.id) == folder_id)
    result = await session.execute(stmt.where(*conditions).order_by(rank, *ordering).limit(limit))
    return list(result.mappings().all())
