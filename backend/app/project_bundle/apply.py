"""Atomic application of validated Project Markdown Bundles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.persistence.model import AgentRunMessage
from app.core.utils.tiktoken import count_tokens
from app.project_bundle.archive import BundleFormatError
from app.project_bundle.importer import (
    ImportMode,
    ParsedBundleCategory,
    ParsedBundleDocument,
    PreviewItem,
    parse_project_bundle,
    preview_project_bundle,
)
from app.storage.models.character import Character
from app.storage.models.note import Note, NoteCategory
from app.storage.models.project import Project
from app.storage.models.task import Task
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry


class BundleApplyConflictError(Exception):
    """Raised when the apply-time preview contains one or more conflicts."""

    def __init__(self, items: list[PreviewItem]) -> None:
        super().__init__("project bundle contains conflicts")
        self.items = items


@dataclass(frozen=True)
class ProjectBundleApplyResult:
    mode: ImportMode
    items: list[PreviewItem]
    summary: dict[str, int]


def _category_depth(
    category: ParsedBundleCategory,
    by_id: dict[str, ParsedBundleCategory],
) -> int:
    depth = 1
    parent_id = category.semantic_fields["parent_id"]
    while parent_id is not None:
        depth += 1
        parent_id = by_id[parent_id].semantic_fields["parent_id"]
    return depth


async def _apply_categories(
    session: AsyncSession,
    categories: list[ParsedBundleCategory],
    actions: dict[tuple[str, str], str],
    now: datetime,
) -> None:
    by_id = {category.id: category for category in categories}
    ordered = sorted(categories, key=lambda item: (_category_depth(item, by_id), item.id))
    for category in ordered:
        action = actions[("note_category", category.id)]
        if action == "unchanged":
            continue
        fields = category.semantic_fields
        if action == "create":
            session.add(
                NoteCategory(
                    id=category.id,
                    project_id=fields["project_id"],
                    parent_id=fields["parent_id"],
                    title=category.title,
                    document_type=fields["document_type"],
                    order=fields["order"],
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            current = await session.get(NoteCategory, category.id)
            if current is None:
                raise BundleFormatError("category disappeared during apply")
            current.parent_id = fields["parent_id"]
            current.title = category.title
            current.document_type = fields["document_type"]
            current.order = fields["order"]
            current.updated_at = now
            session.add(current)
        await session.flush()


async def _ensure_world_book(
    session: AsyncSession,
    project: Project,
    documents: list[ParsedBundleDocument],
    now: datetime,
) -> None:
    world_info_ids = {
        document.semantic_fields["world_info_id"]
        for document in documents
        if document.kind == "world_entry"
    }
    if not world_info_ids:
        return
    world_info_id = next(iter(world_info_ids))
    current = await session.get(WorldInfo, world_info_id)
    if current is None:
        session.add(
            WorldInfo(
                id=world_info_id,
                project_id=project.id,
                name=f"{project.title} 世界书",
                description="",
                created_at=now,
                updated_at=now,
            )
        )
        await session.flush()
    elif current.project_id != project.id:
        raise BundleFormatError("world book id belongs to another project")


async def _apply_world_entry(
    session: AsyncSession,
    document: ParsedBundleDocument,
    action: str,
    now: datetime,
) -> None:
    if action == "unchanged":
        return
    fields = document.semantic_fields
    token_count = count_tokens(document.body, "cl100k_base")
    if action == "create":
        session.add(
            WorldInfoEntry(
                id=document.id,
                world_info_id=fields["world_info_id"],
                uid=fields["uid"],
                name=document.title,
                section=fields["section"],
                order=fields["order"],
                content=document.body,
                token_count=token_count,
                is_enabled=fields["writing_visible"],
                created_at=now,
                updated_at=now,
            )
        )
        return
    current = await session.get(WorldInfoEntry, document.id)
    if current is None:
        raise BundleFormatError("world entry disappeared during apply")
    current.uid = fields["uid"]
    current.name = document.title
    current.section = fields["section"]
    current.order = fields["order"]
    current.content = document.body
    current.token_count = token_count
    current.is_enabled = fields["writing_visible"]
    current.updated_at = now
    session.add(current)


async def _apply_character(
    session: AsyncSession,
    document: ParsedBundleDocument,
    action: str,
    now: datetime,
) -> None:
    if action == "unchanged":
        return
    fields = document.semantic_fields
    if action == "create":
        session.add(
            Character(
                id=document.id,
                project_id=fields["project_id"],
                name=document.title,
                description=document.body,
                order=fields["order"],
                is_writing_visible=fields["writing_visible"],
                is_favorited=fields["is_favorited"],
                created_at=now,
                updated_at=now,
            )
        )
        return
    current = await session.get(Character, document.id)
    if current is None:
        raise BundleFormatError("character disappeared during apply")
    current.name = document.title
    current.description = document.body
    current.order = fields["order"]
    current.is_writing_visible = fields["writing_visible"]
    current.is_favorited = fields["is_favorited"]
    current.updated_at = now
    session.add(current)


async def _apply_note(
    session: AsyncSession,
    document: ParsedBundleDocument,
    action: str,
    now: datetime,
) -> None:
    if action == "unchanged":
        return
    fields = document.semantic_fields
    if action == "create":
        session.add(
            Note(
                id=document.id,
                project_id=fields["project_id"],
                category_id=fields["category_id"],
                title=document.title,
                order=fields["order"],
                content=document.body,
                document_type=fields["document_type"],
                is_locked=fields["is_locked"],
                is_hidden=fields["is_hidden"],
                is_writing_visible=fields["writing_visible"],
                created_at=now,
                updated_at=now,
            )
        )
        return
    current = await session.get(Note, document.id)
    if current is None:
        raise BundleFormatError("note disappeared during apply")
    current.category_id = fields["category_id"]
    current.title = document.title
    current.order = fields["order"]
    current.content = document.body
    current.document_type = fields["document_type"]
    current.is_locked = fields["is_locked"]
    current.is_hidden = fields["is_hidden"]
    current.is_writing_visible = fields["writing_visible"]
    current.updated_at = now
    session.add(current)


async def _apply_discussion(
    session: AsyncSession,
    document: ParsedBundleDocument,
    action: str,
    now: datetime,
) -> None:
    if action == "unchanged":
        return
    fields = document.semantic_fields
    if action == "create":
        session.add(
            Task(
                id=document.id,
                project_id=fields["project_id"],
                title=document.title,
                mode="agent",
                context_mode=fields["context_mode"],
                agent_session_id=None,
                is_imported_archive=True,
                is_running=False,
                created_at=now,
                updated_at=now,
            )
        )
        return
    current = await session.get(Task, document.id)
    if current is None or not current.is_imported_archive:
        raise BundleFormatError("discussion is not an imported archive")
    current.title = document.title
    current.context_mode = fields["context_mode"]
    current.agent_session_id = None
    current.is_running = False
    current.updated_at = now
    session.add(current)


async def _apply_discussion_message(
    session: AsyncSession,
    document: ParsedBundleDocument,
    action: str,
) -> None:
    if action == "unchanged":
        return
    fields = document.semantic_fields
    task = await session.get(Task, fields["discussion_id"])
    if task is None or not task.is_imported_archive or task.agent_session_id is not None:
        raise BundleFormatError("discussion message target is not an imported archive")
    created_at = datetime.fromisoformat(fields["created_at"])
    updated_at = datetime.fromisoformat(fields["updated_at"])
    if action == "create":
        session.add(
            AgentRunMessage(
                id=document.id,
                session_id=task.id,
                task_id=task.id,
                project_id=fields["project_id"],
                role=fields["role"],
                content=document.body,
                status=fields["status"],
                message_type="message",
                display_channel="list",
                llm_visibility="visible",
                seq=fields["seq"],
                created_at=created_at,
                updated_at=updated_at,
            )
        )
        return
    current = await session.get(AgentRunMessage, document.id)
    if current is None or current.task_id != task.id:
        raise BundleFormatError("discussion message disappeared during apply")
    current.session_id = task.id
    current.project_id = fields["project_id"]
    current.role = fields["role"]
    current.content = document.body
    current.status = fields["status"]
    current.message_type = "message"
    current.display_channel = "list"
    current.llm_visibility = "visible"
    current.seq = fields["seq"]
    current.reasoning = None
    current.reasoning_duration_ms = None
    current.tool_calls = None
    current.tool_call_id = None
    current.tool_name = None
    current.message_metadata = "{}"
    current.created_at = created_at
    current.updated_at = updated_at
    session.add(current)


async def apply_project_bundle(
    session: AsyncSession,
    target_project_id: str,
    data: bytes,
    mode: ImportMode,
) -> ProjectBundleApplyResult:
    """Revalidate and atomically stage a conflict-free bundle for commit."""
    preview = await preview_project_bundle(session, target_project_id, data, mode)
    conflicts = [item for item in preview.items if item.action == "conflict"]
    if conflicts:
        raise BundleApplyConflictError(conflicts)

    bundle = parse_project_bundle(data, target_project_id)
    project = await session.get(Project, target_project_id)
    if project is None:
        raise BundleFormatError("project disappeared during apply")
    actions = {(item.kind, item.id): item.action for item in preview.items}
    now = datetime.now(UTC)

    await _apply_categories(session, bundle.note_categories, actions, now)
    await _ensure_world_book(session, project, bundle.documents, now)
    for document in bundle.documents:
        action = actions[(document.kind, document.id)]
        if document.kind == "world_entry":
            await _apply_world_entry(session, document, action, now)
        elif document.kind == "character":
            await _apply_character(session, document, action, now)
        elif document.kind == "note":
            await _apply_note(session, document, action, now)
    await session.flush()

    for document in bundle.documents:
        if document.kind == "discussion":
            await _apply_discussion(session, document, actions[(document.kind, document.id)], now)
    await session.flush()
    for document in bundle.documents:
        if document.kind == "discussion_message":
            await _apply_discussion_message(
                session, document, actions[(document.kind, document.id)]
            )
    await session.flush()

    verified = await preview_project_bundle(session, target_project_id, data, mode)
    if any(item.action != "unchanged" for item in verified.items):
        raise BundleFormatError("post-apply verification failed")
    return ProjectBundleApplyResult(preview.mode, preview.items, preview.summary)
