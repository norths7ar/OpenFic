"""Export project documents to a human-editable Markdown source bundle."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.project_bundle.archive import BundleFormatError, build_zip
from app.project_bundle.names import slugify_filename
from app.storage.models.character import Character
from app.storage.models.note import Note
from app.storage.models.project import Project
from app.storage.models.project_folder import ProjectFolder
from app.storage.models.project_import_binding import ProjectImportBinding
from app.storage.models.project_import_profile import ProjectImportProfile
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry

_ANCHOR_PART = re.compile(r"^H([1-6]):(.+)$")


@dataclass(frozen=True)
class _SourceDocument:
    target_kind: str
    target_id: str
    title: str
    body: str
    writing_visible: bool
    order: int
    section: str | None = None
    category_path: tuple[str, ...] = ()
    category_target_ids: tuple[str, ...] = ()
    category_orders: tuple[int, ...] = ()
    document_type: str | None = None


@dataclass
class _HeadingNode:
    key: str
    level: int
    title: str
    order: int
    body: str = ""
    children: dict[str, _HeadingNode] = field(default_factory=dict)


def default_source_mapping_config() -> dict[str, Any]:
    """Return a portable starting profile whose major sections are optional."""

    return {
        "schema": "openfic.import-map",
        "version": 1,
        "rules": [
            {
                "id": "background",
                "target": "worldbook",
                "source": "背景设定.md",
                "split": {"type": "headings", "item_levels": [2]},
                "required": False,
            },
            {
                "id": "characters",
                "target": "characters",
                "source": "人物.md",
                "split": {"type": "headings", "item_levels": [2]},
                "required": False,
            },
            {
                "id": "outlines",
                "target": "outlines",
                "source": "提纲.md",
                "split": {"type": "headings", "item_levels": [2]},
                "required": False,
            },
            {
                "id": "notes",
                "target": "notes",
                "glob": "笔记/*.md",
                "split": {"type": "file"},
                "required": False,
            },
        ],
    }


def _yaml(value: dict[str, Any]) -> str:
    rendered = yaml.safe_dump(value, allow_unicode=True, sort_keys=False)
    return rendered.rstrip("\n") + "\n"


def _canonical_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """Emit the one-level folder vocabulary while accepting older profiles."""

    result = dict(rule)
    if "folder_level" not in result:
        legacy_levels = result.pop("category_levels", None)
        legacy_section = result.pop("section_level", None)
        if isinstance(legacy_levels, list) and legacy_levels:
            result["folder_level"] = legacy_levels[0]
        elif legacy_section is not None:
            result["folder_level"] = legacy_section
    else:
        result.pop("category_levels", None)
        result.pop("section_level", None)
    if "folder_path" not in result and "category_path" in result:
        result["folder_path"] = result.pop("category_path")
    else:
        result.pop("category_path", None)
    legacy_ids = result.pop("category_target_ids", None)
    if "folder_target_id" not in result and isinstance(legacy_ids, list) and legacy_ids:
        result["folder_target_id"] = legacy_ids[0]
    legacy_orders = result.pop("category_orders", None)
    if "folder_order" not in result and isinstance(legacy_orders, list) and legacy_orders:
        result["folder_order"] = legacy_orders[0]
    return result


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

    documents: dict[tuple[str, str], _SourceDocument] = {}
    for item in entries:
        folder = folders.get(item.folder_id) if item.folder_id else None
        documents[("world_entry", item.id)] = _SourceDocument(
            "world_entry",
            item.id,
            item.name,
            item.content,
            item.is_enabled,
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
            item.is_writing_visible,
            item.order,
            category_path=(folder.title,) if folder else (),
            category_target_ids=(folder.id,) if folder else (),
            category_orders=(folder.order,) if folder else (),
        )
    for item in notes:
        if item.category_id is not None and item.category_id not in category_paths:
            raise BundleFormatError("note category is missing or cross-project")
        documents[("note", item.id)] = _SourceDocument(
            "note",
            item.id,
            item.title,
            item.content,
            item.is_writing_visible,
            item.order,
            category_path=category_paths.get(item.category_id, ()),
            category_target_ids=category_id_paths.get(item.category_id, ()),
            category_orders=category_order_paths.get(item.category_id, ()),
            document_type=item.document_type,
        )
    return project, documents


def _anchor_parts(anchor: str) -> list[tuple[int, str]]:
    parts: list[tuple[int, str]] = []
    for raw in re.split(r"/(?=H[1-6]:)", anchor):
        match = _ANCHOR_PART.fullmatch(raw)
        if match is None:
            raise BundleFormatError("stored source anchor is invalid")
        parts.append((int(match.group(1)), match.group(2)))
    if not parts or parts[0][0] != 1:
        raise BundleFormatError("stored source anchor must start with H1")
    return parts


def _visible_title(document: _SourceDocument, rule: dict[str, Any]) -> str:
    suffix = rule.get("disabled_title_suffix")
    if not document.writing_visible and isinstance(suffix, str):
        return f"{document.title}{suffix}"
    return document.title


def _render_file_source(document: _SourceDocument, rule: dict[str, Any]) -> str:
    title = _visible_title(document, rule)
    return f"# {title}\n\n{document.body}".rstrip() + "\n"


def _render_heading_source(
    records: list[tuple[ProjectImportBinding, _SourceDocument]],
    rule: dict[str, Any],
) -> str:
    roots: dict[str, _HeadingNode] = {}
    folder_level = rule.get("folder_level")
    category_levels = list(rule.get("category_levels", []))
    section_level = rule.get("section_level")
    for binding, document in sorted(records, key=lambda value: value[1].order):
        parts = _anchor_parts(binding.source_anchor)
        effective_levels = [folder_level] if folder_level is not None else category_levels
        dynamic_categories = (
            document.category_path[-len(effective_levels) :] if effective_levels else ()
        )
        category_titles = dict(zip(effective_levels, dynamic_categories, strict=False))
        parent: _HeadingNode | None = None
        for index, (level, anchor_title) in enumerate(parts):
            title = anchor_title
            if level == section_level and document.section:
                title = document.section
            if level in category_titles:
                title = category_titles[level]
            is_leaf = index == len(parts) - 1
            if is_leaf:
                title = _visible_title(document, rule)
            key = f"H{level}:{anchor_title}"
            siblings = roots if parent is None else parent.children
            node = siblings.get(key)
            if node is None:
                node = _HeadingNode(key, level, title, document.order)
                siblings[key] = node
            else:
                node.order = min(node.order, document.order)
                if is_leaf:
                    node.title = title
            if is_leaf:
                node.body = document.body
            parent = node

    lines: list[str] = []

    def emit(node: _HeadingNode) -> None:
        if lines:
            lines.append("")
        lines.append(f"{'#' * node.level} {node.title}")
        if node.body:
            lines.extend(("", node.body))
        children = sorted(node.children.values(), key=lambda value: (value.order, value.key))
        for child in children:
            emit(child)

    for root in sorted(roots.values(), key=lambda value: (value.order, value.key)):
        emit(root)
    return "\n".join(lines).rstrip() + "\n"


def _fallback_path(document: _SourceDocument, document_type: str | None) -> str:
    roots = {
        "world_entry": "背景设定",
        "character": "人物",
        "outline": "提纲",
        "note": "笔记",
    }
    semantic_type = document_type or document.target_kind
    path = PurePosixPath(roots[semantic_type])
    for category in document.category_path:
        path /= slugify_filename(category, "未分类")
    filename = (
        f"{document.order:06d}-"
        f"{slugify_filename(document.title, document.target_id)}"
        f"--{document.target_id}.md"
    )
    return str(path / filename)


def _fallback_rule(
    document: _SourceDocument, source_path: str, document_type: str | None
) -> dict[str, Any]:
    target = {
        "world_entry": "worldbook",
        "character": "characters",
    }.get(document.target_kind, "outlines" if document_type == "outline" else "notes")
    rule: dict[str, Any] = {
        "id": f"openfic-{document.target_kind}-{document.target_id}",
        "target": target,
        "source": source_path,
        "split": {"type": "file"},
        "writing_visible": document.writing_visible,
        "target_id": document.target_id,
        "order": document.order,
    }
    if document.category_path:
        rule["folder_path"] = list(document.category_path)
        rule["folder_target_id"] = document.category_target_ids[0]
        rule["folder_order"] = document.category_orders[0]
    return rule


async def export_markdown_source_bundle(session: AsyncSession, project_id: str) -> bytes:
    """Export mapped documents to their source locations and others by type."""

    _, documents = await _load_documents(session, project_id)
    profile = await session.get(ProjectImportProfile, project_id)
    if profile is None:
        config = default_source_mapping_config()
    else:
        try:
            config = yaml.safe_load(profile.mapping_yaml)
        except yaml.YAMLError as exc:
            raise BundleFormatError("stored import profile is invalid") from exc
        if not isinstance(config, dict) or not isinstance(config.get("rules"), list):
            raise BundleFormatError("stored import profile is invalid")
        config = dict(config)
        config["rules"] = [_canonical_rule(rule) for rule in config["rules"]]

    rules_by_id = {
        rule.get("id"): rule
        for rule in config["rules"]
        if isinstance(rule, dict) and isinstance(rule.get("id"), str)
    }
    bindings = list(
        (
            await session.execute(
                select(ProjectImportBinding).where(
                    col(ProjectImportBinding.project_id) == project_id,
                    col(ProjectImportBinding.target_kind).in_(["world_entry", "character", "note"]),
                )
            )
        ).scalars()
    )
    by_source: dict[tuple[str, str], list[tuple[ProjectImportBinding, _SourceDocument]]] = {}
    mapped_targets: set[tuple[str, str]] = set()
    for binding in bindings:
        rule = rules_by_id.get(binding.rule_id)
        document = documents.get((binding.target_kind, binding.target_id))
        if rule is None or document is None:
            continue
        by_source.setdefault((binding.rule_id, binding.source_path), []).append((binding, document))
        mapped_targets.add((binding.target_kind, binding.target_id))

    files: dict[str, str | bytes] = {}
    rules_with_files: set[str] = set()
    for (rule_id, source_path), records in sorted(by_source.items()):
        rule = rules_by_id[rule_id]
        split = rule.get("split", {})
        if split.get("type") == "file":
            if len(records) != 1:
                raise BundleFormatError("file source maps to multiple project documents")
            files[source_path] = _render_file_source(records[0][1], rule)
        elif split.get("type") == "headings":
            files[source_path] = _render_heading_source(records, rule)
        else:
            raise BundleFormatError("stored import profile has an invalid split")
        rules_with_files.add(rule_id)

    for rule in config["rules"]:
        if rule.get("id") not in rules_with_files:
            rule["required"] = False

    for key, document in sorted(
        documents.items(),
        key=lambda value: (value[1].target_kind, value[1].order, value[0]),
    ):
        if key in mapped_targets:
            continue
        document_type = document.document_type
        source_path = _fallback_path(document, document_type)
        files[source_path] = _render_file_source(document, {})
        config["rules"].append(_fallback_rule(document, source_path, document_type))

    # A dormant template glob must not also import the explicit fallback documents.
    config["rules"] = [
        rule
        for rule in config["rules"]
        if rule.get("id") in rules_with_files
        or "glob" not in rule
        or not any(fnmatch.fnmatchcase(path, rule["glob"]) for path in files)
    ]
    files["openfic-import.yaml"] = _yaml(config)
    return build_zip(files)
