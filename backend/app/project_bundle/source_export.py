"""Export project documents to a human-editable Markdown source bundle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.agent_visibility import (
    DEFAULT_AGENT_VISIBILITY,
    AgentVisibility,
)
from app.project_bundle.archive import BundleFormatError, build_zip
from app.project_bundle.names import slugify_filename
from app.storage.models.chapter import Chapter
from app.storage.models.character import Character
from app.storage.models.note import Note
from app.storage.models.project import Project
from app.storage.models.project_folder import ProjectFolder
from app.storage.models.project_import_binding import ProjectImportBinding
from app.storage.models.project_import_profile import ProjectImportProfile
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry


@dataclass(frozen=True)
class _SourceDocument:
    target_kind: str
    target_id: str
    title: str
    body: str
    agent_visibility: AgentVisibility
    order: int
    section: str | None = None
    category_path: tuple[str, ...] = ()
    category_target_ids: tuple[str, ...] = ()
    category_orders: tuple[int, ...] = ()
    document_type: str | None = None
    is_locked: bool = False
    is_favorited: bool = False


def default_source_mapping_config() -> dict[str, Any]:
    """Version 2 uses independent directory roots for each document type."""
    return {
        "schema": "openfic.import-map",
        "version": 2,
        "rules": [
            {"id": target, "target": target, "source": root, "layout": "files", "required": False}
            for target, root in (
                ("chapters", "正文"),
                ("worldbook", "背景设定"),
                ("characters", "角色"),
                ("outlines", "提纲"),
                ("notes", "笔记"),
            )
        ],
    }


def _yaml(value: dict[str, Any]) -> str:
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False).rstrip("\n") + "\n"


def _category_paths(
    categories: list[ProjectFolder],
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]], dict[str, tuple[int, ...]]]:
    return (
        {folder.id: (folder.title,) for folder in categories},
        {folder.id: (folder.id,) for folder in categories},
        {folder.id: (folder.order,) for folder in categories},
    )


async def _load_documents(
    session: AsyncSession, project_id: str
) -> tuple[Project, dict[tuple[str, str], _SourceDocument]]:
    project = await session.get(Project, project_id)
    if project is None:
        raise BundleFormatError(f"project not found: {project_id}")

    world = (
        await session.execute(select(WorldInfo).where(col(WorldInfo.project_id) == project_id))
    ).scalar_one_or_none()
    entries = (
        []
        if world is None
        else list(
            (
                await session.execute(
                    select(WorldInfoEntry)
                    .where(col(WorldInfoEntry.world_info_id) == world.id)
                    .order_by(col(WorldInfoEntry.order), col(WorldInfoEntry.id))
                )
            ).scalars()
        )
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
                select(ProjectFolder).where(
                    col(ProjectFolder.project_id) == project_id,
                    col(ProjectFolder.scope).in_(["note", "outline"]),
                )
            )
        ).scalars()
    )
    category_paths, category_id_paths, category_order_paths = _category_paths(categories)
    folders = {
        folder.id: folder
        for folder in (
            await session.execute(
                select(ProjectFolder).where(col(ProjectFolder.project_id) == project_id)
            )
        ).scalars()
    }
    notes = list(
        (
            await session.execute(
                select(Note)
                .where(col(Note.project_id) == project_id)
                .order_by(col(Note.order), col(Note.id))
            )
        ).scalars()
    )
    chapters = list(
        (
            await session.execute(
                select(Chapter)
                .where(col(Chapter.project_id) == project_id)
                .order_by(col(Chapter.volume_id), col(Chapter.order), col(Chapter.id))
            )
        ).scalars()
    )

    documents: dict[tuple[str, str], _SourceDocument] = {}
    for item in entries:
        folder = folders.get(item.folder_id) if item.folder_id else None
        documents[("world_entry", item.id)] = _SourceDocument(
            "world_entry",
            item.id,
            item.name,
            item.content,
            item.agent_visibility,
            item.order,
            section=item.section,
            category_path=(folder.title,) if folder else (),
            category_target_ids=(folder.id,) if folder else (),
            category_orders=(folder.order,) if folder else (),
        )
    for item in characters:
        folder = folders.get(item.folder_id) if item.folder_id else None
        documents[("character", item.id)] = _SourceDocument(
            "character",
            item.id,
            item.name,
            item.description,
            item.agent_visibility,
            item.order,
            category_path=(folder.title,) if folder else (),
            category_target_ids=(folder.id,) if folder else (),
            category_orders=(folder.order,) if folder else (),
            is_favorited=item.is_favorited,
        )
    for item in notes:
        if item.category_id is not None and item.category_id not in category_paths:
            raise BundleFormatError("note category is missing or cross-project")
        documents[("note", item.id)] = _SourceDocument(
            "note",
            item.id,
            item.title,
            item.content,
            item.agent_visibility,
            item.order,
            category_path=category_paths.get(item.category_id, ()),
            category_target_ids=category_id_paths.get(item.category_id, ()),
            category_orders=category_order_paths.get(item.category_id, ()),
            document_type=item.document_type,
            is_locked=item.is_locked,
        )
    for item in chapters:
        folder = folders.get(item.volume_id) if item.volume_id else None
        if item.volume_id is not None and (folder is None or folder.scope != "writing"):
            raise BundleFormatError("chapter volume is missing or cross-project")
        documents[("chapter", item.id)] = _SourceDocument(
            "chapter",
            item.id,
            item.title,
            item.content,
            DEFAULT_AGENT_VISIBILITY,
            item.order,
            category_path=(folder.title,) if folder else (),
            category_target_ids=(folder.id,) if folder else (),
            category_orders=(folder.order,) if folder else (),
        )
    return project, documents


def _document_target(document: _SourceDocument) -> str:
    return {
        "world_entry": "worldbook",
        "character": "characters",
        "chapter": "chapters",
    }.get(document.target_kind, "outlines" if document.document_type == "outline" else "notes")


async def export_markdown_source_bundle(session: AsyncSession, project_id: str) -> bytes:
    """Write v2 only; legacy profiles remain importable, never constrain content."""
    from .directory_mapping import TARGET_SCOPES, directory_rules
    from .item_markers import render_item

    _, documents = await _load_documents(session, project_id)
    profile = await session.get(ProjectImportProfile, project_id)
    config = default_source_mapping_config()
    if profile is not None:
        try:
            stored = yaml.safe_load(profile.mapping_yaml)
        except yaml.YAMLError as exc:
            raise BundleFormatError("stored import profile is invalid") from exc
        if not isinstance(stored, dict):
            raise BundleFormatError("stored import profile is invalid")
        if stored.get("version") == 2:
            directory_rules(stored)
            config = {**stored, "rules": [dict(rule) for rule in stored["rules"]]}
        # Heading-based v1 mappings cannot express the new directory contract.
        # Export them into the portable default roots, without mutating profile/data.
    for default in default_source_mapping_config()["rules"]:
        if not any(rule["target"] == default["target"] for rule in config["rules"]):
            # Defaults must never reserve names against user-owned mappings.
            # Choose a sibling root, not a child of an existing mapped root.
            roots = [rule["source"].casefold() for rule in config["rules"]]
            source = default["source"]
            suffix = 2
            while any(
                source.casefold() == root
                or source.casefold().startswith(root + "/")
                or root.startswith(source.casefold() + "/")
                for root in roots
            ):
                source = f"{default['source']}-{suffix}"
                suffix += 1
            rule_id = "openfic-" + default["id"]
            existing_ids = {rule["id"] for rule in config["rules"]}
            suffix = 2
            while rule_id in existing_ids:
                rule_id = f"openfic-{default['id']}-{suffix}"
                suffix += 1
            config["rules"].append({**default, "id": rule_id, "source": source})
    rules = directory_rules(config)
    bindings = list(
        (
            await session.execute(
                select(ProjectImportBinding).where(
                    col(ProjectImportBinding.project_id) == project_id
                )
            )
        ).scalars()
    )
    bound = {
        (row.target_kind, row.target_id): row
        for row in sorted(bindings, key=lambda row: row.updated_at)
    }
    rules_by_id = {rule["id"]: rule for rule in rules}

    def rule_for(document: _SourceDocument) -> dict[str, Any]:
        binding = bound.get((document.target_kind, document.target_id))
        rule = rules_by_id.get(binding.rule_id) if binding else None
        target = _document_target(document)
        return (
            rule
            if rule is not None and rule["target"] == target
            else next(candidate for candidate in rules if candidate["target"] == target)
        )

    folders = list(
        (
            await session.execute(
                select(ProjectFolder)
                .where(
                    col(ProjectFolder.project_id) == project_id,
                    col(ProjectFolder.scope).in_(list(TARGET_SCOPES.values())),
                )
                .order_by(col(ProjectFolder.scope), col(ProjectFolder.order), col(ProjectFolder.id))
            )
        ).scalars()
    )
    folder_sources: dict[str, str] = {}
    config.pop("items", None)
    previous_folders = {folder["id"]: folder for folder in config.get("folders", [])}
    config["folders"] = []
    used_directories: set[str] = set()
    for folder in folders:
        members = [
            document
            for document in documents.values()
            if document.category_target_ids == (folder.id,)
        ]
        member_rules = {rule_for(document)["id"] for document in members}
        previous = previous_folders.get(folder.id, {})
        if len(member_rules) > 1:
            raise BundleFormatError("one project folder cannot span multiple mapping roots")
        rule = (
            rules_by_id[next(iter(member_rules))]
            if member_rules
            else next(
                (
                    candidate
                    for candidate in rules
                    if previous.get("source", "").startswith(candidate["source"] + "/")
                ),
                next(
                    candidate
                    for candidate in rules
                    if TARGET_SCOPES[candidate["target"]] == folder.scope
                ),
            )
        )
        directory = str(PurePosixPath(rule["source"]) / slugify_filename(folder.title, folder.id))
        if directory.casefold() in used_directories:
            directory += "--" + folder.id
        used_directories.add(directory.casefold())
        folder_sources[folder.id] = directory
        config["folders"].append(
            {
                "id": folder.id,
                "scope": folder.scope,
                "title": folder.title,
                "order": folder.order,
                "description": folder.description,
                "source": directory,
            }
        )
    files: dict[str, str | bytes] = {}
    for document in sorted(
        documents.values(), key=lambda item: (_document_target(item), item.order, item.target_id)
    ):
        rule = rule_for(document)
        directory = (
            folder_sources[document.category_target_ids[0]]
            if document.category_target_ids
            else rule["source"]
        )
        if rule.get("layout", "files") == "merged":
            filename = "条目.md"
        else:
            filename = f"{document.order:06d}-{slugify_filename(document.title, document.target_id)}--{document.target_id}.md"
        path = str(PurePosixPath(directory) / filename)
        metadata: dict[str, Any] = {
            "id": document.target_id,
            "title": document.title,
            "order": document.order,
            "agent_visibility": document.agent_visibility.value,
        }
        if document.target_kind == "world_entry":
            metadata["section"] = document.section or ""
        elif document.target_kind == "character":
            metadata["is_favorited"] = document.is_favorited
        elif document.target_kind == "note":
            metadata["is_locked"] = document.is_locked
        files[path] = str(files.get(path, "")) + render_item(metadata, document.body)
    files["openfic-import.yaml"] = _yaml(config)
    return build_zip(files)
