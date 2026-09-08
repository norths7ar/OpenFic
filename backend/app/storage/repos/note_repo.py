"""
Note Repository - 笔记数据访问层。
"""

from sqlalchemy import case as sa_case
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.agent_visibility import AgentVisibility
from app.storage.models.note import Note


async def create(session: AsyncSession, note: Note) -> Note:
    session.add(note)
    await session.flush()
    await session.refresh(note)
    return note


async def get_by_id(session: AsyncSession, note_id: str) -> Note | None:
    result = await session.execute(select(Note).where(col(Note.id) == note_id))
    return result.scalar_one_or_none()


async def get_max_order(
    session: AsyncSession,
    project_id: str,
    category_id: str | None,
    document_type: str = "note",
) -> int:
    statement = select(func.max(col(Note.order))).where(
        col(Note.project_id) == project_id,
        col(Note.document_type) == document_type,
    )
    if category_id is None:
        statement = statement.where(col(Note.category_id).is_(None))
    else:
        statement = statement.where(col(Note.category_id) == category_id)
    result = await session.execute(statement)
    return int(result.scalar_one_or_none() or 0)


async def list_by_project(
    session: AsyncSession,
    project_id: str,
    *,
    include_hidden: bool = True,
    document_type: str | None = None,
) -> list[Note]:
    stmt = (
        select(Note)
        .where(col(Note.project_id) == project_id)
        .order_by(col(Note.order).asc(), col(Note.title).asc(), col(Note.id).asc())
    )
    if not include_hidden:
        stmt = stmt.where(col(Note.agent_visibility) != AgentVisibility.NONE)
    if document_type is not None:
        stmt = stmt.where(col(Note.document_type) == document_type)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def search_mention_candidates(
    session: AsyncSession,
    project_id: str,
    query: str,
    *,
    limit: int,
    include_hidden: bool = False,
) -> list[Note]:
    normalized_query = query.strip().lower()
    if not normalized_query:
        return []

    title_expr = func.lower(func.coalesce(col(Note.title), ""))
    match_rank = sa_case(
        (title_expr == normalized_query, 0),
        (title_expr.like(f"{normalized_query}%"), 1),
        (title_expr.contains(normalized_query), 2),
        else_=99,
    )

    stmt = (
        select(Note)
        .where(
            col(Note.project_id) == project_id,
            title_expr.contains(normalized_query),
        )
        .order_by(match_rank.asc(), col(Note.title).asc())
        .limit(limit)
    )
    if not include_hidden:
        stmt = stmt.where(col(Note.agent_visibility) != AgentVisibility.NONE)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def search_by_content(
    session: AsyncSession,
    project_id: str,
    query: str,
    document_type: str | None = None,
) -> list[Note]:
    """按笔记内容搜索笔记。"""
    normalized_query = query.strip()
    if not normalized_query:
        return []

    statement = select(Note).where(
        col(Note.project_id) == project_id,
        col(Note.content).ilike(f"%{normalized_query}%"),
    )
    if document_type is not None:
        statement = statement.where(col(Note.document_type) == document_type)
    result = await session.execute(
        statement.order_by(col(Note.order).asc(), col(Note.title).asc(), col(Note.id).asc())
    )
    return list(result.scalars().all())


async def update_note(session: AsyncSession, note: Note) -> Note:
    session.add(note)
    await session.flush()
    await session.refresh(note)
    return note


async def delete(session: AsyncSession, note: Note) -> None:
    await session.delete(note)
    await session.flush()
