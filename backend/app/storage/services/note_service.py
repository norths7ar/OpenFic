"""
Note Service - 笔记业务逻辑层。
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.editor_content_limits import validate_editor_content
from app.core.errors import ConflictError, NotFoundError
from app.storage.models.note import Note
from app.storage.models.project_folder import ProjectFolder
from app.storage.repos import (
    note_category_repo,
    note_repo,
    project_repo,
)
from app.storage.services import project_folder_service, writing_activity_service

DocumentType = Literal["note", "outline"]


@dataclass
class NoteCategoryNode:
    category: ProjectFolder
    sub_categories: list["NoteCategoryNode"] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)


@dataclass
class NoteTreeResult:
    categories: list[NoteCategoryNode]
    root_notes: list[Note]
    total_notes: int


async def _get_max_mixed_order(
    session: AsyncSession,
    project_id: str,
    parent_id: str | None,
    document_type: DocumentType,
) -> int:
    categories = await note_category_repo.list_by_project(session, project_id, document_type)
    notes = await note_repo.list_by_project(
        session,
        project_id,
        include_hidden=True,
        document_type=document_type,
    )
    orders = [category.order for category in categories if parent_id is None]
    orders.extend(note.order for note in notes if note.category_id == parent_id)
    return max(orders, default=0)


async def create_note(
    session: AsyncSession,
    project_id: str,
    category_id: str | None,
    title: str,
    content: str = "",
    document_type: DocumentType = "note",
) -> Note:
    validate_editor_content(content)
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        raise NotFoundError(f"项目不存在: {project_id}")

    if category_id is not None:
        category = await note_category_repo.get_by_id(session, category_id)
        if category is None:
            raise NotFoundError(f"分类不存在: {category_id}")
        if category.project_id != project_id:
            raise ValueError("分类不属于当前项目")
        if category.scope != document_type:
            raise ValueError("条目与分类的文档类型不一致")

    notes = await note_repo.list_by_project(
        session,
        project_id,
        include_hidden=True,
        document_type=document_type,
    )
    siblings = {n.title for n in notes if n.category_id == category_id}
    unique_title = title
    counter = 1
    while unique_title in siblings:
        unique_title = f"{title}({counter})"
        counter += 1

    note = Note(
        project_id=project_id,
        category_id=category_id,
        title=unique_title,
        content=content,
        document_type=document_type,
        order=await _get_max_mixed_order(session, project_id, category_id, document_type) + 1,
        is_writing_visible=True,
    )
    note = await note_repo.create(session, note)

    await writing_activity_service.record_activity(
        session,
        project_id=project_id,
        chapter_id=note.id,
        chapter_title=note.title,
        source="user",
        operation="create",
        old_word_count=0,
        new_word_count=0,
    )
    return note


async def get_note(session: AsyncSession, note_id: str) -> Note:
    note = await note_repo.get_by_id(session, note_id)
    if note is None:
        raise NotFoundError(f"笔记不存在: {note_id}")
    return note


async def list_notes(
    session: AsyncSession,
    project_id: str,
    document_type: DocumentType = "note",
) -> NoteTreeResult:
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        raise NotFoundError(f"项目不存在: {project_id}")

    categories = await note_category_repo.list_by_project(session, project_id, document_type)
    notes = await note_repo.list_by_project(
        session,
        project_id,
        include_hidden=True,
        document_type=document_type,
    )

    notes_by_category: dict[str | None, list[Note]] = {}
    for note in notes:
        notes_by_category.setdefault(note.category_id, []).append(note)

    def build_node(cat: ProjectFolder) -> NoteCategoryNode:
        return NoteCategoryNode(
            category=cat,
            sub_categories=[],
            notes=notes_by_category.get(cat.id, []),
        )

    tree_nodes = [build_node(category) for category in categories]
    root_notes = notes_by_category.get(None, [])

    return NoteTreeResult(
        categories=tree_nodes,
        root_notes=root_notes,
        total_notes=len(notes),
    )


async def reorder_items(
    session: AsyncSession,
    project_id: str,
    *,
    item_kind: Literal["category", "note"],
    parent_id: str | None,
    ordered_ids: list[str],
    document_type: DocumentType = "note",
) -> int:
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        raise NotFoundError(f"项目不存在: {project_id}")
    if len(ordered_ids) != len(set(ordered_ids)):
        raise ValueError("ordered_ids 不能包含重复 ID")
    if parent_id is not None:
        parent = await note_category_repo.get_by_id(session, parent_id)
        if parent is None or parent.project_id != project_id:
            raise ValueError("父分类不存在或不属于当前项目")
        if parent.scope != document_type:
            raise ValueError("父分类与当前文档类型不一致")

    if item_kind == "category":
        siblings = [
            category
            for category in await note_category_repo.list_by_project(
                session, project_id, document_type
            )
            if parent_id is None
        ]
    else:
        siblings = [
            note
            for note in await note_repo.list_by_project(
                session, project_id, document_type=document_type
            )
            if note.category_id == parent_id
        ]
    expected = {item.id for item in siblings}
    if set(ordered_ids) != expected or len(ordered_ids) != len(expected):
        raise ValueError("ordered_ids 必须完整匹配当前同级条目")
    now = datetime.now(UTC)
    by_id = {item.id: item for item in siblings}
    for index, item_id in enumerate(ordered_ids):
        item = by_id[item_id]
        item.order = index
        item.updated_at = now
        session.add(item)
    await session.flush()
    return len(ordered_ids)


async def reorder_mixed_items(
    session: AsyncSession,
    project_id: str,
    *,
    parent_id: str | None,
    ordered_items: list[tuple[Literal["category", "note"], str]],
    document_type: DocumentType = "note",
) -> int:
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        raise NotFoundError(f"项目不存在: {project_id}")
    if len(ordered_items) != len(set(ordered_items)):
        raise ValueError("ordered_items 不能包含重复条目")
    if parent_id is not None:
        parent = await note_category_repo.get_by_id(session, parent_id)
        if parent is None or parent.project_id != project_id:
            raise ValueError("父分类不存在或不属于当前项目")
        if parent.scope != document_type:
            raise ValueError("父分类与当前文档类型不一致")

    categories = [
        category
        for category in await note_category_repo.list_by_project(session, project_id, document_type)
        if parent_id is None
    ]
    notes = [
        note
        for note in await note_repo.list_by_project(
            session,
            project_id,
            include_hidden=True,
            document_type=document_type,
        )
        if note.category_id == parent_id
    ]
    siblings: dict[tuple[Literal["category", "note"], str], Note | ProjectFolder] = {
        **{("category", item.id): item for item in categories},
        **{("note", item.id): item for item in notes},
    }
    if set(ordered_items) != set(siblings) or len(ordered_items) != len(siblings):
        raise ValueError("ordered_items 必须完整匹配当前同级分类和条目")

    now = datetime.now(UTC)
    for index, key in enumerate(ordered_items):
        item = siblings[key]
        item.order = index
        item.updated_at = now
        session.add(item)
    await session.flush()
    return len(ordered_items)


async def update_note(
    session: AsyncSession,
    note_id: str,
    title: str | None = None,
    content: str | None = None,
    is_writing_visible: bool | None = None,
    is_hidden: bool | None = None,
) -> Note:
    note = await get_note(session, note_id)
    changed = False
    records_writing_activity = False

    changes_locked_content = (title is not None and title != note.title) or (
        content is not None and content != note.content
    )
    if note.is_locked and changes_locked_content:
        raise ConflictError("笔记已锁定，请先解锁")

    if title is not None and title != note.title:
        note.title = title
        changed = True
        records_writing_activity = True

    if content is not None and content != note.content:
        validate_editor_content(content)
        note.content = content
        changed = True
        records_writing_activity = True

    if is_writing_visible is not None and is_writing_visible != note.is_writing_visible:
        note.is_writing_visible = is_writing_visible
        changed = True

    if is_hidden is not None and is_hidden != note.is_hidden:
        note.is_hidden = is_hidden
        changed = True

    if changed:
        note.updated_at = datetime.now(UTC)
        note = await note_repo.update_note(session, note)
        if records_writing_activity:
            await writing_activity_service.record_activity(
                session,
                project_id=note.project_id,
                chapter_id=note.id,
                chapter_title=note.title,
                source="user",
                operation="update",
                old_word_count=0,
                new_word_count=0,
            )
    return note


async def delete_note(
    session: AsyncSession,
    note_id: str,
) -> None:
    note = await get_note(session, note_id)
    if note.is_locked:
        raise ConflictError("笔记已锁定，请先解锁")
    project_id = note.project_id
    old_title = note.title
    await note_repo.delete(session, note)
    await writing_activity_service.record_activity(
        session,
        project_id=project_id,
        chapter_id=note_id,
        chapter_title=old_title,
        source="user",
        operation="delete",
        old_word_count=0,
        new_word_count=0,
    )


async def set_note_locked(
    session: AsyncSession,
    note_id: str,
    is_locked: bool,
) -> Note:
    note = await get_note(session, note_id)
    if note.is_locked != is_locked:
        note.is_locked = is_locked
        note.updated_at = datetime.now(UTC)
        note = await note_repo.update_note(session, note)
        await writing_activity_service.record_activity(
            session,
            project_id=note.project_id,
            chapter_id=note.id,
            chapter_title=note.title,
            source="user",
            operation="update",
            old_word_count=0,
            new_word_count=0,
        )
    return note


async def set_note_hidden(
    session: AsyncSession,
    note_id: str,
    is_hidden: bool,
) -> Note:
    note = await get_note(session, note_id)
    if note.is_hidden != is_hidden:
        note.is_hidden = is_hidden
        note.updated_at = datetime.now(UTC)
        note = await note_repo.update_note(session, note)
        await writing_activity_service.record_activity(
            session,
            project_id=note.project_id,
            chapter_id=note.id,
            chapter_title=note.title,
            source="user",
            operation="update",
            old_word_count=0,
            new_word_count=0,
        )
    return note


async def create_category(
    session: AsyncSession,
    project_id: str,
    parent_id: str | None,
    title: str,
    document_type: DocumentType = "note",
) -> ProjectFolder:
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        raise NotFoundError(f"项目不存在: {project_id}")

    if parent_id is not None:
        raise ValueError("文件夹只支持一层")

    return await project_folder_service.create_folder(session, project_id, document_type, title)


async def update_category(
    session: AsyncSession,
    category_id: str,
    title: str | None,
) -> ProjectFolder:
    category = await note_category_repo.get_by_id(session, category_id)
    if category is None:
        raise NotFoundError(f"分类不存在: {category_id}")

    if title is not None and title != category.title:
        category.title = title
        category.updated_at = datetime.now(UTC)
        category = await note_category_repo.update_category(session, category)
    return category


async def delete_category(
    session: AsyncSession,
    category_id: str,
) -> None:
    category = await note_category_repo.get_by_id(session, category_id)
    if category is None:
        raise NotFoundError(f"文件夹不存在: {category_id}")
    await project_folder_service.delete_folder(session, category_id)


async def move_item(
    session: AsyncSession,
    item_kind: Literal["category", "note"],
    item_id: str,
    target_category_id: str | None,
) -> Note | ProjectFolder:
    if item_kind == "category":
        category = await note_category_repo.get_by_id(session, item_id)
        if category is None:
            raise NotFoundError(f"分类不存在: {item_id}")

        if target_category_id is not None:
            raise ValueError("文件夹只支持一层")

        category.updated_at = datetime.now(UTC)
        category = await note_category_repo.update_category(session, category)

        await writing_activity_service.record_activity(
            session,
            project_id=category.project_id,
            chapter_id=category.id,
            chapter_title=category.title,
            source="user",
            operation="update",
            old_word_count=0,
            new_word_count=0,
        )
        return category

    else:
        note = await note_repo.get_by_id(session, item_id)
        if note is None:
            raise NotFoundError(f"笔记不存在: {item_id}")
        if note.is_locked:
            raise ConflictError("笔记已锁定，请先解锁")

        if target_category_id is not None:
            target = await note_category_repo.get_by_id(session, target_category_id)
            if target is None or target.project_id != note.project_id:
                raise ValueError("目标分类不存在或不属于当前项目")
            if target.scope != note.document_type:
                raise ValueError("不能跨文档类型移动条目")

        if note.category_id != target_category_id:
            note.category_id = target_category_id
            note.order = (
                await _get_max_mixed_order(
                    session,
                    note.project_id,
                    target_category_id,
                    cast(DocumentType, note.document_type),
                )
                + 1
            )
        note.updated_at = datetime.now(UTC)
        note = await note_repo.update_note(session, note)

        await writing_activity_service.record_activity(
            session,
            project_id=note.project_id,
            chapter_id=note.id,
            chapter_title=note.title,
            source="user",
            operation="update",
            old_word_count=0,
            new_word_count=0,
        )
        return note


async def search_mention_candidates(
    session: AsyncSession,
    project_id: str,
    query: str,
    *,
    limit: int,
) -> list:
    from app.storage.services.mention_service import (
        search_all_mention_candidates,
    )

    return await search_all_mention_candidates(session, project_id, query, limit=limit, kind="note")


@dataclass
class NoteSearchMatch:
    """笔记内容搜索匹配行。"""

    line_number: int
    line_text: str


@dataclass
class NoteSearchResult:
    """笔记内容搜索结果。"""

    note_id: str
    note_title: str
    category_path: str
    matches: list[NoteSearchMatch]


@dataclass
class NoteSearchResponse:
    """笔记内容搜索响应。"""

    results: list[NoteSearchResult]
    total_notes: int
    total_matches: int


async def _build_category_path(
    session: AsyncSession,
    category_id: str | None,
) -> str:
    """构建分类路径字符串。"""
    if category_id is None:
        return ""
    parts: list[str] = []
    current_id: str | None = category_id
    while current_id is not None:
        cat = await note_category_repo.get_by_id(session, current_id)
        if cat is None:
            break
        parts.append(cat.title or "未命名分类")
        current_id = None
    parts.reverse()
    return " / ".join(parts)


async def search_notes(
    session: AsyncSession,
    project_id: str,
    query: str,
    document_type: DocumentType = "note",
) -> NoteSearchResponse:
    """按内容搜索笔记。"""
    project = await project_repo.get_by_id(session, project_id)
    if project is None:
        raise NotFoundError(f"项目不存在: {project_id}")

    if not query.strip():
        return NoteSearchResponse(results=[], total_notes=0, total_matches=0)

    notes = await note_repo.search_by_content(session, project_id, query, document_type)

    results: list[NoteSearchResult] = []
    total_matches = 0
    lower_query = query.lower()

    for note in notes:
        lines = note.content.split("\n")
        matches: list[NoteSearchMatch] = []
        for line_number, line in enumerate(lines, start=1):
            if lower_query in line.lower():
                matches.append(
                    NoteSearchMatch(
                        line_number=line_number,
                        line_text=line,
                    )
                )

        if matches:
            category_path = await _build_category_path(session, note.category_id)
            results.append(
                NoteSearchResult(
                    note_id=note.id,
                    note_title=note.title or "未命名笔记",
                    category_path=category_path,
                    matches=matches,
                )
            )
            total_matches += len(matches)

    return NoteSearchResponse(
        results=results,
        total_notes=len(results),
        total_matches=total_matches,
    )
