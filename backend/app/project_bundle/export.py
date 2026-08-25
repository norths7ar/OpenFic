"""Deterministic, read-only Project Markdown Bundle v1 export."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.agent_runtime.persistence.model import AgentRunMessage
from app.project_bundle.archive import BundleFormatError, build_zip
from app.project_bundle.markdown import render_markdown_document
from app.project_bundle.names import slugify_filename
from app.storage.models.character import Character
from app.storage.models.note import Note, NoteCategory
from app.storage.models.project import Project
from app.storage.models.task import Task
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry


def semantic_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=True).rstrip("\n") + "\n"


def _doc(frontmatter: dict[str, Any], title: str, body: str) -> str:
    return render_markdown_document(frontmatter, title, body)


def document_semantic_hash(fields: dict[str, Any], title: str, body: str) -> str:
    return semantic_hash({**fields, "title": title, "body": body})


def _category_paths(categories: Iterable[NoteCategory]) -> dict[str, str]:
    by_id = {item.id: item for item in categories}
    paths: dict[str, str] = {}

    def build(category_id: str, stack: tuple[str, ...] = ()) -> str:
        if category_id in paths:
            return paths[category_id]
        if category_id in stack:
            raise BundleFormatError("note category hierarchy contains a cycle")
        category = by_id[category_id]
        if category.parent_id is None:
            parent = PurePosixPath("notes")
        else:
            parent_category = by_id.get(category.parent_id)
            if (
                parent_category is None
                or parent_category.project_id != category.project_id
            ):
                raise BundleFormatError(
                    "note category parent is missing or cross-project"
                )
            parent = PurePosixPath(build(category.parent_id, (*stack, category_id)))
        segment = (
            f"{category.order:06d}-{slugify_filename(category.title, category.id)}"
            f"--{category.id}"
        )
        paths[category_id] = str(parent / segment)
        return paths[category_id]

    for category_id in by_id:
        build(category_id)
    return paths


async def export_project_bundle(session: AsyncSession, project_id: str) -> bytes:
    project = await session.get(Project, project_id)
    if project is None:
        raise BundleFormatError(f"project not found: {project_id}")

    world_info = (
        await session.execute(
            select(WorldInfo).where(col(WorldInfo.project_id) == project_id)
        )
    ).scalar_one_or_none()
    entries: list[WorldInfoEntry] = []
    if world_info is not None:
        entries = list(
            (
                await session.execute(
                    select(WorldInfoEntry)
                    .where(col(WorldInfoEntry.world_info_id) == world_info.id)
                    .order_by(col(WorldInfoEntry.order), col(WorldInfoEntry.id))
                )
            ).scalars()
        )
    characters = list(
        (
            await session.execute(
                select(Character)
                .where(col(Character.project_id) == project_id)
                .order_by(col(Character.order), col(Character.id))
            )
        ).scalars()
    )
    categories = list(
        (
            await session.execute(
                select(NoteCategory)
                .where(col(NoteCategory.project_id) == project_id)
                .order_by(col(NoteCategory.order), col(NoteCategory.id))
            )
        ).scalars()
    )
    category_paths = _category_paths(categories)
    notes = list(
        (
            await session.execute(
                select(Note)
                .where(col(Note.project_id) == project_id)
                .order_by(col(Note.order), col(Note.id))
            )
        ).scalars()
    )

    files: dict[str, str | bytes] = {}
    documents: list[dict[str, Any]] = []
    for entry in entries:
        fields = {
            "kind": "world_entry",
            "id": entry.id,
            "project_id": project_id,
            "world_info_id": entry.world_info_id,
            "uid": entry.uid,
            "section": entry.section,
            "order": entry.order,
            "writing_visible": entry.is_enabled,
        }
        path = (
            f"worldbook/{entry.order:06d}-{slugify_filename(entry.name, entry.id)}"
            f"--{entry.id}.md"
        )
        base_hash = document_semantic_hash(fields, entry.name, entry.content)
        files[path] = _doc(
            {
                "schema": "openfic.document",
                "version": 1,
                **fields,
                "base_hash": base_hash,
            },
            entry.name,
            entry.content,
        )
        documents.append(
            {
                "kind": "world_entry",
                "id": entry.id,
                "path": path,
                "base_hash": base_hash,
            }
        )
    for character in characters:
        fields = {
            "kind": "character",
            "id": character.id,
            "project_id": project_id,
            "order": character.order,
            "writing_visible": character.is_writing_visible,
            "is_favorited": character.is_favorited,
        }
        path = (
            f"characters/{character.order:06d}-"
            f"{slugify_filename(character.name, character.id)}"
            f"--{character.id}.md"
        )
        base_hash = document_semantic_hash(
            fields, character.name, character.description
        )
        files[path] = _doc(
            {
                "schema": "openfic.document",
                "version": 1,
                **fields,
                "base_hash": base_hash,
            },
            character.name,
            character.description,
        )
        documents.append(
            {
                "kind": "character",
                "id": character.id,
                "path": path,
                "base_hash": base_hash,
            }
        )
    for note in notes:
        fields = {
            "kind": "note",
            "id": note.id,
            "project_id": project_id,
            "category_id": note.category_id,
            "order": note.order,
            "writing_visible": note.is_writing_visible,
            "is_locked": note.is_locked,
            "is_hidden": note.is_hidden,
        }
        if note.category_id is not None and note.category_id not in category_paths:
            raise BundleFormatError("note category is missing or cross-project")
        directory = category_paths.get(note.category_id, "notes/_uncategorized")
        path = (
            f"{directory}/{note.order:06d}-{slugify_filename(note.title, note.id)}"
            f"--{note.id}.md"
        )
        base_hash = document_semantic_hash(fields, note.title, note.content)
        files[path] = _doc(
            {
                "schema": "openfic.document",
                "version": 1,
                **fields,
                "base_hash": base_hash,
            },
            note.title,
            note.content,
        )
        documents.append(
            {"kind": "note", "id": note.id, "path": path, "base_hash": base_hash}
        )

    tasks = list(
        (
            await session.execute(
                select(Task)
                .where(
                    col(Task.project_id) == project_id,
                    col(Task.agent_session_id).is_not(None),
                )
                .order_by(col(Task.created_at), col(Task.id))
            )
        ).scalars()
    )
    for index, task in enumerate(tasks, start=1):
        session_id = task.agent_session_id
        assert session_id is not None
        directory = (
            f"discussions/{index:06d}-{slugify_filename(task.title, task.id)}"
            f"--{task.id}"
        )
        discussion_fields = {
            "kind": "discussion",
            "id": task.id,
            "project_id": project_id,
            "context_mode": task.context_mode,
        }
        discussion_hash = document_semantic_hash(discussion_fields, task.title, "")
        discussion_path = f"{directory}/discussion.md"
        files[discussion_path] = _doc(
            {
                "schema": "openfic.document",
                "version": 1,
                **discussion_fields,
                "base_hash": discussion_hash,
            },
            task.title,
            "",
        )
        documents.append(
            {
                "kind": "discussion",
                "id": task.id,
                "path": discussion_path,
                "base_hash": discussion_hash,
            }
        )
        messages = list(
            (
                await session.execute(
                    select(AgentRunMessage)
                    .where(
                        col(AgentRunMessage.project_id) == project_id,
                        col(AgentRunMessage.task_id) == task.id,
                        col(AgentRunMessage.session_id) == session_id,
                        col(AgentRunMessage.role).in_(["user", "assistant"]),
                        col(AgentRunMessage.display_channel) == "list",
                        col(AgentRunMessage.content) != "",
                        col(AgentRunMessage.status) != "pending",
                    )
                    .order_by(col(AgentRunMessage.seq), col(AgentRunMessage.id))
                )
            ).scalars()
        )
        for message in messages:
            label = "用户" if message.role == "user" else "助手"
            message_fields = {
                "kind": "discussion_message",
                "id": message.id,
                "project_id": project_id,
                "discussion_id": task.id,
                "seq": message.seq,
                "role": message.role,
                "status": message.status,
                "created_at": message.created_at.isoformat(),
                "updated_at": message.updated_at.isoformat(),
            }
            message_hash = document_semantic_hash(
                {
                    key: value
                    for key, value in message_fields.items()
                    if key not in {"created_at", "updated_at"}
                },
                f"{label} {message.seq:06d}",
                message.content,
            )
            path = (
                f"{directory}/messages/{message.seq:06d}-{message.role}"
                f"--{message.id}.md"
            )
            files[path] = _doc(
                {
                    "schema": "openfic.document",
                    "version": 1,
                    **message_fields,
                    "base_hash": message_hash,
                },
                f"{label} {message.seq:06d}",
                message.content,
            )
            documents.append(
                {
                    "kind": "discussion_message",
                    "id": message.id,
                    "path": path,
                    "base_hash": message_hash,
                }
            )

    categories_manifest = [
        {
            "id": c.id,
            "project_id": c.project_id,
            "parent_id": c.parent_id,
            "title": c.title,
            "order": c.order,
            "base_hash": semantic_hash(
                {
                    "kind": "note_category",
                    "id": c.id,
                    "project_id": c.project_id,
                    "parent_id": c.parent_id,
                    "title": c.title,
                    "order": c.order,
                }
            ),
        }
        for c in categories
    ]
    manifest = {
        "schema": "openfic.project-bundle",
        "version": 1,
        "project": {
            "id": project.id,
            "title": project.title,
            "description": project.description or "",
        },
        "documents": sorted(documents, key=lambda item: item["path"]),
        "note_categories": categories_manifest,
    }
    files["openfic.yaml"] = _yaml(manifest)
    return build_zip(files)
