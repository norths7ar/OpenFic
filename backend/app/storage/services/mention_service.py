"""Mention search and browsing, with one visibility boundary before pagination."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.knowledge_scope import KnowledgeScope
from app.storage.repos import mention_repo, project_repo
from app.storage.repos.mention_repo import MentionKind


@dataclass(frozen=True)
class MentionCandidate:
    kind: MentionKind
    id: str
    title: str
    label: str
    description: str | None = None
    folder_id: str | None = None
    folder_name: str | None = None


@dataclass(frozen=True)
class MentionFolder:
    id: str
    title: str


@dataclass(frozen=True)
class MentionPage:
    items: list[MentionCandidate]
    folders: list[MentionFolder]
    has_more: bool


async def search_mention_page(
    session: AsyncSession,
    project_id: str,
    query: str,
    *,
    limit: int = 20,
    offset: int = 0,
    kind: MentionKind | None = None,
    context_mode: KnowledgeScope = KnowledgeScope.LOCAL,
    folder_id: str | None = None,
) -> MentionPage:
    if await project_repo.get_by_id(session, project_id) is None:
        raise NotFoundError(f"项目不存在: {project_id}")

    normalized_query = query.strip().lower()
    clamped_limit = max(1, min(limit, 50))
    offset = max(0, offset)
    fetch_limit = offset + clamped_limit + 1
    context_mode = KnowledgeScope(context_mode)
    kinds = [kind] if kind is not None else list(mention_repo.FOLDER_SCOPES)
    scored: list[tuple[int, int, int, MentionCandidate]] = []
    for kind_index, candidate_kind in enumerate(kinds):
        rows = await mention_repo.search_by_kind(
            session,
            project_id,
            candidate_kind,
            normalized_query,
            context_mode=context_mode,
            folder_id=folder_id,
            limit=fetch_limit,
        )
        for index, row in enumerate(rows):
            title = row["title"].strip() or "未命名"
            candidate = MentionCandidate(
                kind=candidate_kind,
                id=row["id"],
                title=title,
                label=title,
                description=row["folder_name"],
                folder_id=row["folder_id"],
                folder_name=row["folder_name"],
            )
            # Empty browsing interleaves kinds; searches retain relevance priority.
            score = (row["rank"], kind_index, index) if normalized_query else (0, index, kind_index)
            scored.append((*score, candidate))

    scored.sort(key=lambda item: item[:3])
    folders = await mention_repo.list_folders(session, project_id, kind)
    return MentionPage(
        items=[item[3] for item in scored[offset : offset + clamped_limit]],
        folders=[MentionFolder(id=folder.id, title=folder.title) for folder in folders],
        has_more=len(scored) > offset + clamped_limit,
    )


async def search_all_mention_candidates(
    session: AsyncSession,
    project_id: str,
    query: str,
    *,
    limit: int = 20,
    offset: int = 0,
    kind: MentionKind | None = None,
    context_mode: KnowledgeScope = KnowledgeScope.LOCAL,
    folder_id: str | None = None,
) -> list[MentionCandidate]:
    """Retain the list-returning service entry point for existing callers."""
    page = await search_mention_page(
        session,
        project_id,
        query,
        limit=limit,
        offset=offset,
        kind=kind,
        context_mode=context_mode,
        folder_id=folder_id,
    )
    return page.items
