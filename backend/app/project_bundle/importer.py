"""Strict Project Markdown Bundle v1 parser and read-only preview."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.agent_runtime.persistence.model import AgentRunMessage
from app.core.editor_content_limits import validate_editor_content
from app.core.errors import NotFoundError
from app.project_bundle.archive import BundleFormatError, read_zip
from app.project_bundle.export import document_semantic_hash, semantic_hash
from app.project_bundle.markdown import parse_markdown_document
from app.storage.models.character import Character
from app.storage.models.note import Note, NoteCategory
from app.storage.models.project import Project
from app.storage.models.task import Task
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry

ImportMode = Literal["append", "update", "merge"]
_KINDS = {"world_entry", "character", "note", "discussion", "discussion_message"}
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class ParsedBundleDocument:
    kind: str
    id: str
    title: str
    body: str
    base_hash: str
    semantic_fields: dict[str, Any]
    path: str


@dataclass(frozen=True)
class ParsedBundleCategory:
    id: str
    title: str
    base_hash: str
    semantic_fields: dict[str, Any]


@dataclass(frozen=True)
class ParsedProjectBundle:
    source_project: dict[str, Any]
    documents: list[ParsedBundleDocument]
    note_categories: list[ParsedBundleCategory]


@dataclass(frozen=True)
class PreviewItem:
    kind: str
    id: str
    title: str
    path: str
    action: str
    reason: str
    base_hash: str
    current_hash: str | None
    incoming_hash: str


@dataclass(frozen=True)
class ProjectBundlePreview:
    mode: ImportMode
    source_project: dict[str, Any]
    items: list[PreviewItem]
    summary: dict[str, int]


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise BundleFormatError(f"{field} must be a non-empty string")
    return value


def _int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BundleFormatError(f"{field} must be an integer")
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    result = _int(value, field)
    if result < 0:
        raise BundleFormatError(f"{field} must be non-negative")
    return result


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise BundleFormatError(f"{field} must be a boolean")
    return value


def _nullable_text(value: Any, field: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise BundleFormatError(f"{field} must be a string or null")
    return value


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise BundleFormatError(f"{field} must be a string")
    return value


def _hash(value: Any, field: str) -> str:
    result = _text(value, field)
    if _HASH.fullmatch(result) is None:
        raise BundleFormatError(f"{field} must be a sha256 hash")
    return result


def _document_fields(
    frontmatter: dict[str, Any], kind: str, project_id: str
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "kind": kind,
        "id": _text(frontmatter.get("id"), "id"),
        "project_id": project_id,
    }
    if kind == "world_entry":
        fields.update(
            world_info_id=_text(frontmatter.get("world_info_id"), "world_info_id"),
            uid=_int(frontmatter.get("uid"), "uid"),
            section=_string(frontmatter.get("section"), "section"),
            order=_nonnegative_int(frontmatter.get("order"), "order"),
            writing_visible=_bool(
                frontmatter.get("writing_visible"), "writing_visible"
            ),
        )
    elif kind == "character":
        fields.update(
            order=_nonnegative_int(frontmatter.get("order"), "order"),
            writing_visible=_bool(
                frontmatter.get("writing_visible"), "writing_visible"
            ),
            is_favorited=_bool(frontmatter.get("is_favorited"), "is_favorited"),
        )
    elif kind == "note":
        fields.update(
            category_id=_nullable_text(frontmatter.get("category_id"), "category_id"),
            order=_nonnegative_int(frontmatter.get("order"), "order"),
            writing_visible=_bool(
                frontmatter.get("writing_visible"), "writing_visible"
            ),
            is_locked=_bool(frontmatter.get("is_locked"), "is_locked"),
            is_hidden=_bool(frontmatter.get("is_hidden"), "is_hidden"),
        )
    elif kind == "discussion":
        context_mode = frontmatter.get("context_mode")
        if context_mode not in {"global", "local"}:
            raise BundleFormatError("context_mode must be global or local")
        fields["context_mode"] = context_mode
    elif kind == "discussion_message":
        role = frontmatter.get("role")
        if role not in {"user", "assistant"}:
            raise BundleFormatError("discussion_message role is invalid")
        fields.update(
            discussion_id=_text(frontmatter.get("discussion_id"), "discussion_id"),
            seq=_nonnegative_int(frontmatter.get("seq"), "seq"),
            role=role,
            status=_text(frontmatter.get("status"), "status"),
        )
        for name in ("created_at", "updated_at"):
            value = _text(frontmatter.get(name), name)
            try:
                parsed_datetime = datetime.fromisoformat(value)
            except ValueError as exc:
                raise BundleFormatError(f"{name} must be an ISO datetime") from exc
            if parsed_datetime.tzinfo is None or parsed_datetime.utcoffset() is None:
                raise BundleFormatError(f"{name} must include a timezone")
            fields[name] = value
    return fields


def parse_project_bundle(data: bytes, target_project_id: str) -> ParsedProjectBundle:
    files = read_zip(data)
    manifest_bytes = files.get("openfic.yaml")
    if manifest_bytes is None:
        raise BundleFormatError("openfic.yaml is required")
    try:
        manifest = yaml.safe_load(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise BundleFormatError("openfic.yaml must be UTF-8 YAML") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != "openfic.project-bundle"
        or manifest.get("version") != 1
    ):
        raise BundleFormatError("unsupported project bundle manifest")
    project = manifest.get("project")
    if not isinstance(project, dict) or project.get("id") != target_project_id:
        raise BundleFormatError("bundle project does not match target project")
    source_project = {
        "id": _text(project.get("id"), "project id"),
        "title": _text(project.get("title"), "project title"),
        "description": _string(project.get("description"), "project description"),
    }
    documents = manifest.get("documents")
    categories = manifest.get("note_categories")
    if not isinstance(documents, list) or not isinstance(categories, list):
        raise BundleFormatError("documents and note_categories must be lists")
    listed_paths: set[str] = set()
    listed_keys: set[tuple[str, str]] = set()
    parsed: list[ParsedBundleDocument] = []
    for item in documents:
        if not isinstance(item, dict):
            raise BundleFormatError("document manifest item must be a mapping")
        path = _text(item.get("path"), "document path")
        kind = _text(item.get("kind"), "document kind")
        doc_id = _text(item.get("id"), "document id")
        base_hash = _hash(item.get("base_hash"), "document base_hash")
        if kind not in _KINDS or path in listed_paths or (kind, doc_id) in listed_keys:
            raise BundleFormatError("invalid or duplicate document manifest item")
        if path == "openfic.yaml" or path not in files:
            raise BundleFormatError("document manifest path is missing from archive")
        listed_paths.add(path)
        listed_keys.add((kind, doc_id))
        try:
            parsed_doc = parse_markdown_document(files[path].decode("utf-8"))
        except (UnicodeDecodeError, BundleFormatError) as exc:
            raise BundleFormatError(f"invalid document: {path}") from exc
        fm = parsed_doc.frontmatter
        if fm.get("schema") != "openfic.document" or fm.get("version") != 1:
            raise BundleFormatError(f"invalid document schema: {path}")
        if (
            fm.get("kind") != kind
            or fm.get("id") != doc_id
            or fm.get("project_id") != target_project_id
            or fm.get("base_hash") != base_hash
        ):
            raise BundleFormatError(f"document identity mismatch: {path}")
        fields = _document_fields(fm, kind, target_project_id)
        if len(parsed_doc.title) > 200:
            raise BundleFormatError("document H1 exceeds 200 characters")
        if kind == "world_entry":
            if fields["uid"] < 1:
                raise BundleFormatError("uid must be positive")
            if len(fields["section"]) > 500:
                raise BundleFormatError("section exceeds 500 characters")
        if kind in {"world_entry", "character", "note", "discussion_message"}:
            try:
                validate_editor_content(parsed_doc.body)
            except ValueError as exc:
                raise BundleFormatError(str(exc)) from exc
        if kind == "discussion" and parsed_doc.body:
            raise BundleFormatError("discussion document body must be empty")
        if kind == "discussion_message":
            if len(fields["status"]) > 20:
                raise BundleFormatError("discussion message status is too long")
            if fields["status"] == "pending":
                raise BundleFormatError(
                    "pending discussion messages cannot be imported"
                )
            label = "用户" if fields["role"] == "user" else "助手"
            if parsed_doc.title != f"{label} {fields['seq']:06d}":
                raise BundleFormatError("discussion message H1 is not canonical")
        parsed.append(
            ParsedBundleDocument(
                kind, doc_id, parsed_doc.title, parsed_doc.body, base_hash, fields, path
            )
        )
    if set(files) - {"openfic.yaml"} != listed_paths:
        raise BundleFormatError("archive contains an unlisted document")

    parsed_categories: list[ParsedBundleCategory] = []
    category_ids: set[str] = set()
    for item in categories:
        if not isinstance(item, dict):
            raise BundleFormatError("category manifest item must be a mapping")
        category_id = _text(item.get("id"), "category id")
        if category_id in category_ids or item.get("project_id") != target_project_id:
            raise BundleFormatError("invalid or duplicate category")
        parent_id = _nullable_text(item.get("parent_id"), "parent_id")
        title = _text(item.get("title"), "category title")
        order = _nonnegative_int(item.get("order"), "category order")
        base_hash = _hash(item.get("base_hash"), "category base_hash")
        fields = {
            "kind": "note_category",
            "id": category_id,
            "project_id": target_project_id,
            "parent_id": parent_id,
            "title": title,
            "order": order,
        }
        category_ids.add(category_id)
        parsed_categories.append(
            ParsedBundleCategory(category_id, title, base_hash, fields)
        )
    for category in parsed_categories:
        parent_id = category.semantic_fields["parent_id"]
        if parent_id is not None and parent_id not in category_ids:
            raise BundleFormatError("category parent is missing")
    for category in parsed_categories:
        seen: set[str] = set()
        current: str | None = category.id
        depth = 0
        while current is not None:
            if current in seen:
                raise BundleFormatError("category hierarchy contains a cycle")
            seen.add(current)
            depth += 1
            if depth > 2:
                raise BundleFormatError("category hierarchy exceeds two levels")
            current = next(
                (
                    c.semantic_fields["parent_id"]
                    for c in parsed_categories
                    if c.id == current
                ),
                None,
            )
    category_names: set[tuple[str | None, str]] = set()
    for category in parsed_categories:
        name_key = (category.semantic_fields["parent_id"], category.title)
        if name_key in category_names:
            raise BundleFormatError("note category name is duplicated among siblings")
        category_names.add(name_key)

    discussions = {doc.id for doc in parsed if doc.kind == "discussion"}
    message_positions: set[tuple[str, int]] = set()
    world_names: set[str] = set()
    world_uids: set[int] = set()
    character_names: set[str] = set()
    note_names: set[tuple[str | None, str]] = set()
    for doc in parsed:
        if (
            doc.kind == "note"
            and doc.semantic_fields["category_id"] is not None
            and doc.semantic_fields["category_id"] not in category_ids
        ):
            raise BundleFormatError("note category is missing")
        if (
            doc.kind == "discussion_message"
            and doc.semantic_fields["discussion_id"] not in discussions
        ):
            raise BundleFormatError("discussion message parent is missing")
        if doc.kind == "discussion_message":
            position = (
                doc.semantic_fields["discussion_id"],
                doc.semantic_fields["seq"],
            )
            if position in message_positions:
                raise BundleFormatError("discussion message seq is duplicated")
            message_positions.add(position)
        if doc.kind == "world_entry":
            if doc.title in world_names:
                raise BundleFormatError("world entry name is duplicated")
            if doc.semantic_fields["uid"] in world_uids:
                raise BundleFormatError("world entry uid is duplicated")
            world_names.add(doc.title)
            world_uids.add(doc.semantic_fields["uid"])
        elif doc.kind == "character":
            if doc.title in character_names:
                raise BundleFormatError("character name is duplicated")
            character_names.add(doc.title)
        elif doc.kind == "note":
            note_key = (doc.semantic_fields["category_id"], doc.title)
            if note_key in note_names:
                raise BundleFormatError("note title is duplicated in a category")
            note_names.add(note_key)

    world_info_ids = {
        doc.semantic_fields["world_info_id"]
        for doc in parsed
        if doc.kind == "world_entry"
    }
    if len(world_info_ids) > 1:
        raise BundleFormatError("bundle contains multiple world books")
    return ParsedProjectBundle(source_project, parsed, parsed_categories)


async def preview_project_bundle(
    session: AsyncSession, target_project_id: str, data: bytes, mode: ImportMode
) -> ProjectBundlePreview:
    project = await session.get(Project, target_project_id)
    if project is None:
        raise NotFoundError(f"项目不存在：{target_project_id}")
    if mode not in {"append", "update", "merge"}:
        raise BundleFormatError("invalid preview mode")
    bundle = parse_project_bundle(data, target_project_id)
    target_world = (
        await session.execute(
            select(WorldInfo).where(col(WorldInfo.project_id) == target_project_id)
        )
    ).scalar_one_or_none()
    items: list[PreviewItem] = []
    for category in bundle.note_categories:
        current = await session.get(NoteCategory, category.id)
        current_hash = None
        if current is not None:
            if current.project_id != target_project_id:
                current_hash = "cross-project"
            else:
                current_hash = semantic_hash(
                    {
                        "kind": "note_category",
                        "id": current.id,
                        "project_id": current.project_id,
                        "parent_id": current.parent_id,
                        "title": current.title,
                        "order": current.order,
                    }
                )
        item = _action(
            mode,
            "note_category",
            category.id,
            category.title,
            "",
            category.base_hash,
            current_hash,
            semantic_hash(category.semantic_fields),
        )
        if await _has_name_conflict(
            session,
            kind="note_category",
            entity_id=category.id,
            title=category.title,
            fields=category.semantic_fields,
            project_id=target_project_id,
        ):
            item = replace(item, action="conflict", reason="same_name_different_id")
        items.append(item)
    for doc in bundle.documents:
        current_hash, current_project_ok = await _current_hash(
            session, doc, target_project_id
        )
        if not current_project_ok:
            current_hash = "cross-project"
        incoming_fields = doc.semantic_fields
        if doc.kind == "discussion_message":
            incoming_fields = {
                key: value
                for key, value in incoming_fields.items()
                if key not in {"created_at", "updated_at"}
            }
        incoming_hash = document_semantic_hash(incoming_fields, doc.title, doc.body)
        item = _action(
            mode,
            doc.kind,
            doc.id,
            doc.title,
            doc.path,
            doc.base_hash,
            current_hash,
            incoming_hash,
        )
        if await _has_name_conflict(
            session,
            kind=doc.kind,
            entity_id=doc.id,
            title=doc.title,
            fields=doc.semantic_fields,
            project_id=target_project_id,
        ):
            item = replace(item, action="conflict", reason="same_name_different_id")
        if doc.kind == "world_entry":
            incoming_world = await session.get(
                WorldInfo, doc.semantic_fields["world_info_id"]
            )
            if (
                incoming_world is not None
                and incoming_world.project_id != target_project_id
            ):
                item = replace(
                    item, action="conflict", reason="cross_project_world_book_id"
                )
            elif (
                target_world is not None
                and doc.semantic_fields["world_info_id"] != target_world.id
            ):
                item = replace(item, action="conflict", reason="world_book_id_mismatch")
            elif await _has_world_uid_conflict(
                session,
                world_info_id=doc.semantic_fields["world_info_id"],
                entry_id=doc.id,
                uid=doc.semantic_fields["uid"],
            ):
                item = replace(item, action="conflict", reason="same_uid_different_id")
        if item.action in {"create", "update"} and await _targets_live_discussion(
            session, doc, target_project_id
        ):
            item = replace(
                item, action="conflict", reason="live_discussion_is_read_only"
            )
        items.append(item)
    summary = {
        key: sum(item.action == key for item in items)
        for key in ("create", "update", "unchanged", "conflict")
    }
    return ProjectBundlePreview(mode, bundle.source_project, items, summary)


async def _has_world_uid_conflict(
    session: AsyncSession,
    *,
    world_info_id: str,
    entry_id: str,
    uid: int,
) -> bool:
    statement = select(col(WorldInfoEntry.id)).where(
        col(WorldInfoEntry.world_info_id) == world_info_id,
        col(WorldInfoEntry.uid) == uid,
        col(WorldInfoEntry.id) != entry_id,
    )
    return (await session.execute(statement.limit(1))).scalar_one_or_none() is not None


async def _targets_live_discussion(
    session: AsyncSession,
    doc: ParsedBundleDocument,
    project_id: str,
) -> bool:
    if doc.kind == "discussion":
        task_id = doc.id
    elif doc.kind == "discussion_message":
        task_id = doc.semantic_fields["discussion_id"]
    else:
        return False
    task = await session.get(Task, task_id)
    return bool(
        task is not None
        and task.project_id == project_id
        and not task.is_imported_archive
    )


async def _has_name_conflict(
    session: AsyncSession,
    *,
    kind: str,
    entity_id: str,
    title: str,
    fields: dict[str, Any],
    project_id: str,
) -> bool:
    if kind == "world_entry":
        world = (
            await session.execute(
                select(WorldInfo).where(col(WorldInfo.project_id) == project_id)
            )
        ).scalar_one_or_none()
        if world is None:
            return False
        statement = select(col(WorldInfoEntry.id)).where(
            col(WorldInfoEntry.world_info_id) == world.id,
            col(WorldInfoEntry.name) == title,
            col(WorldInfoEntry.id) != entity_id,
        )
    elif kind == "character":
        statement = select(col(Character.id)).where(
            col(Character.project_id) == project_id,
            col(Character.name) == title,
            col(Character.id) != entity_id,
        )
    elif kind == "note":
        category_id = fields["category_id"]
        category_filter = (
            col(Note.category_id).is_(None)
            if category_id is None
            else col(Note.category_id) == category_id
        )
        statement = select(col(Note.id)).where(
            col(Note.project_id) == project_id,
            category_filter,
            col(Note.title) == title,
            col(Note.id) != entity_id,
        )
    elif kind == "note_category":
        parent_id = fields["parent_id"]
        parent_filter = (
            col(NoteCategory.parent_id).is_(None)
            if parent_id is None
            else col(NoteCategory.parent_id) == parent_id
        )
        statement = select(col(NoteCategory.id)).where(
            col(NoteCategory.project_id) == project_id,
            parent_filter,
            col(NoteCategory.title) == title,
            col(NoteCategory.id) != entity_id,
        )
    else:
        return False
    return (await session.execute(statement.limit(1))).scalar_one_or_none() is not None


def _action(
    mode: ImportMode,
    kind: str,
    doc_id: str,
    title: str,
    path: str,
    base_hash: str,
    current_hash: str | None,
    incoming_hash: str,
) -> PreviewItem:
    if current_hash == "cross-project":
        action, reason = "conflict", "cross_project_id"
    elif current_hash is None:
        action, reason = (
            ("create", "not_found")
            if mode in {"append", "merge"}
            else ("conflict", "missing_for_update")
        )
    elif current_hash == incoming_hash:
        action, reason = "unchanged", "same_semantics"
    elif mode == "append":
        action, reason = "conflict", "existing_differs"
    elif current_hash == base_hash:
        action, reason = "update", "current_matches_base"
    else:
        action, reason = "conflict", "current_changed"
    return PreviewItem(
        kind,
        doc_id,
        title,
        path,
        action,
        reason,
        base_hash,
        current_hash,
        incoming_hash,
    )


async def _current_hash(
    session: AsyncSession, doc: ParsedBundleDocument, project_id: str
) -> tuple[str | None, bool]:
    if doc.kind == "world_entry":
        current = await session.get(WorldInfoEntry, doc.id)
        if current is None:
            return None, True
        world = await session.get(WorldInfo, current.world_info_id)
        if world is None or world.project_id != project_id:
            return None, False
        fields = {
            "kind": "world_entry",
            "id": current.id,
            "project_id": project_id,
            "world_info_id": current.world_info_id,
            "uid": current.uid,
            "section": current.section,
            "order": current.order,
            "writing_visible": current.is_enabled,
        }
        return document_semantic_hash(fields, current.name, current.content), True
    if doc.kind == "character":
        current = await session.get(Character, doc.id)
        if current is None:
            return None, True
        if current.project_id != project_id:
            return None, False
        fields = {
            "kind": "character",
            "id": current.id,
            "project_id": project_id,
            "order": current.order,
            "writing_visible": current.is_writing_visible,
            "is_favorited": current.is_favorited,
        }
        return document_semantic_hash(fields, current.name, current.description), True
    if doc.kind == "note":
        current = await session.get(Note, doc.id)
        if current is None:
            return None, True
        if current.project_id != project_id:
            return None, False
        fields = {
            "kind": "note",
            "id": current.id,
            "project_id": project_id,
            "category_id": current.category_id,
            "order": current.order,
            "writing_visible": current.is_writing_visible,
            "is_locked": current.is_locked,
            "is_hidden": current.is_hidden,
        }
        return document_semantic_hash(fields, current.title, current.content), True
    if doc.kind == "discussion":
        current = await session.get(Task, doc.id)
        if current is None:
            return None, True
        if current.project_id != project_id:
            return None, False
        fields = {
            "kind": "discussion",
            "id": current.id,
            "project_id": project_id,
            "context_mode": current.context_mode,
        }
        return document_semantic_hash(fields, current.title, ""), True
    current = await session.get(AgentRunMessage, doc.id)
    if current is None:
        return None, True
    task = await session.get(Task, current.task_id)
    if (
        task is None
        or task.project_id != project_id
        or current.project_id != project_id
    ):
        return None, False
    if not task.is_imported_archive and current.session_id != task.agent_session_id:
        return None, False
    fields = {
        "kind": "discussion_message",
        "id": current.id,
        "project_id": project_id,
        "discussion_id": task.id,
        "seq": current.seq,
        "role": current.role,
        "status": current.status,
        "created_at": current.created_at.isoformat(),
        "updated_at": current.updated_at.isoformat(),
    }
    fields_for_hash = {
        key: value
        for key, value in fields.items()
        if key not in {"created_at", "updated_at"}
    }
    label = "用户" if current.role == "user" else "助手"
    return document_semantic_hash(
        fields_for_hash, f"{label} {current.seq:06d}", current.content
    ), True
