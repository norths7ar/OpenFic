"""Deterministic, read-only Project Markdown Bundle v1 export."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
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
from app.storage.models.note import Note
from app.storage.models.project import Project
from app.storage.models.project_folder import ProjectFolder
from app.storage.models.task import Task
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry


def semantic_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=True).rstrip("\n") + "\n"


def _doc(frontmatter: dict[str, Any], title: str, body: str) -> str:
    return render_markdown_document(frontmatter, title, body)


def document_semantic_hash(fields: dict[str, Any], title: str, body: str) -> str:
    return semantic_hash({**fields, "title": title, "body": body})


def _iso_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _category_paths(categories: Iterable[ProjectFolder]) -> dict[str, str]:
    return {
        folder.id: str(
            PurePosixPath("outlines" if folder.scope == "outline" else "notes")
            / f"{folder.order:06d}-{slugify_filename(folder.title, folder.id)}--{folder.id}"
        )
        for folder in categories
    }


async def export_project_bundle(session: AsyncSession, project_id: str) -> bytes:
    project = await session.get(Project, project_id)
    if project is None:
        raise BundleFormatError(f"project not found: {project_id}")

    project_folders = list(
        (
            await session.execute(
                select(ProjectFolder)
                .where(
                    col(ProjectFolder.project_id) == project_id,
                    col(ProjectFolder.scope).in_(["discussion", "world", "character"]),
                )
                .order_by(col(ProjectFolder.scope), col(ProjectFolder.order), col(ProjectFolder.id))
            )
        ).scalars()
    )

    world_info = (
        await session.execute(select(WorldInfo).where(col(WorldInfo.project_id) == project_id))
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
                select(ProjectFolder)
                .where(
                    col(ProjectFolder.project_id) == project_id,
                    col(ProjectFolder.scope).in_(["note", "outline"]),
                )
                .order_by(col(ProjectFolder.order), col(ProjectFolder.id))
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
            "agent_visibility": entry.agent_visibility,
            "folder_id": entry.folder_id,
        }
        path = (
            f"worldbook/{entry.order:06d}-{slugify_filename(entry.name, entry.id)}--{entry.id}.md"
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
            "agent_visibility": character.agent_visibility,
            "is_favorited": character.is_favorited,
            "folder_id": character.folder_id,
        }
        path = (
            f"characters/{character.order:06d}-"
            f"{slugify_filename(character.name, character.id)}"
            f"--{character.id}.md"
        )
        base_hash = document_semantic_hash(fields, character.name, character.description)
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
            "document_type": note.document_type,
            "order": note.order,
            "agent_visibility": note.agent_visibility,
            "is_locked": note.is_locked,
        }
        if note.category_id is not None and note.category_id not in category_paths:
            raise BundleFormatError("note category is missing or cross-project")
        root_directory = "outlines" if note.document_type == "outline" else "notes"
        directory = category_paths.get(note.category_id, f"{root_directory}/_uncategorized")
        path = f"{directory}/{note.order:06d}-{slugify_filename(note.title, note.id)}--{note.id}.md"
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
        documents.append({"kind": "note", "id": note.id, "path": path, "base_hash": base_hash})

    tasks = list(
        (
            await session.execute(
                select(Task)
                .where(
                    col(Task.project_id) == project_id,
                    (
                        col(Task.agent_session_id).is_not(None)
                        | col(Task.is_imported_archive).is_(True)
                    ),
                )
                .order_by(col(Task.created_at), col(Task.id))
            )
        ).scalars()
    )
    for index, task in enumerate(tasks, start=1):
        session_id = task.agent_session_id
        directory = f"discussions/{index:06d}-{slugify_filename(task.title, task.id)}--{task.id}"
        discussion_fields = {
            "kind": "discussion",
            "id": task.id,
            "project_id": project_id,
            "context_mode": task.context_mode,
            "folder_id": task.folder_id,
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
                        *(
                            [col(AgentRunMessage.session_id) == session_id]
                            if session_id is not None
                            else []
                        ),
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
                "created_at": _iso_datetime(message.created_at),
                "updated_at": _iso_datetime(message.updated_at),
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
            path = f"{directory}/messages/{message.seq:06d}-{message.role}--{message.id}.md"
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
            "parent_id": None,
            "title": c.title,
            **({"description": c.description} if c.description is not None else {}),
            "document_type": c.scope,
            "order": c.order,
            "base_hash": semantic_hash(
                {
                    "kind": "note_category",
                    "id": c.id,
                    "project_id": c.project_id,
                    "parent_id": None,
                    "title": c.title,
                    **({"description": c.description} if c.description is not None else {}),
                    "document_type": c.scope,
                    "order": c.order,
                }
            ),
        }
        for c in categories
    ]
    folders_manifest = [
        {
            "id": folder.id,
            "project_id": folder.project_id,
            "scope": folder.scope,
            "title": folder.title,
            **({"description": folder.description} if folder.description is not None else {}),
            "order": folder.order,
            "base_hash": semantic_hash(
                {
                    "kind": "project_folder",
                    "id": folder.id,
                    "project_id": folder.project_id,
                    "scope": folder.scope,
                    "title": folder.title,
                    **(
                        {"description": folder.description}
                        if folder.description is not None
                        else {}
                    ),
                    "order": folder.order,
                }
            ),
        }
        for folder in project_folders
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
        "project_folders": folders_manifest,
    }
    files["openfic.yaml"] = _yaml(manifest)
    return build_zip(files)
