"""Convert declaratively mapped Markdown sources into Native Bundle v1."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.errors import NotFoundError
from app.project_bundle.archive import BundleFormatError, build_zip
from app.project_bundle.export import document_semantic_hash, semantic_hash
from app.project_bundle.markdown import render_markdown_document
from app.project_bundle.names import slugify_filename
from app.project_bundle.source_mapping import (
    MappedSourceItem,
    _source_metadata,
    parse_source_mapping,
    read_source_mapping_manifest,
)
from app.storage.models.character import Character
from app.storage.models.note import Note
from app.storage.models.project import Project
from app.storage.models.project_import_binding import ProjectImportBinding
from app.storage.models.project_import_profile import ProjectImportProfile
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry

_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_TARGET_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CATEGORY_RULE_ID = "__mapped_categories__"
_FOLDER_RULE_ID = "__mapped_folders__"


@dataclass(frozen=True)
class MappedBindingSpec:
    binding_key: str
    rule_id: str
    source_path: str
    source_anchor: str
    target_kind: str
    target_id: str
    incoming_hash: str


@dataclass(frozen=True)
class MappedProjectBundle:
    data: bytes
    source_items: list[MappedSourceItem]
    bindings: list[MappedBindingSpec]


def _yaml(value: dict[str, Any]) -> str:
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=True).rstrip("\n") + "\n"


def _identity_key(
    project_id: str,
    rule_id: str,
    source_path: str,
    source_anchor: str,
    target_kind: str,
) -> str:
    payload = "\0".join((project_id, rule_id, source_path, source_anchor, target_kind))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _generated_id(target_kind: str, binding_key: str) -> str:
    prefixes = {
        "world_entry": "map-we",
        "character": "map-ch",
        "note": "map-no",
        "note_category": "map-nc",
        "project_folder": "map-pf",
    }
    return f"{prefixes[target_kind]}-{binding_key[:24]}"


def _binding_metadata_matches(
    binding: ProjectImportBinding,
    *,
    rule_id: str,
    source_path: str,
    source_anchor: str,
    target_kind: str,
) -> bool:
    return (
        binding.rule_id == rule_id
        and binding.source_path == source_path
        and binding.source_anchor == source_anchor
        and binding.target_kind == target_kind
    )


def _base_hash(
    binding: ProjectImportBinding | None,
    incoming_hash: str,
) -> str:
    if binding is None:
        return incoming_hash
    value = binding.last_applied_hash
    if _HASH.fullmatch(value) is None:
        raise BundleFormatError("stored import baseline hash is invalid")
    return value


class _Builder:
    def __init__(
        self,
        *,
        project: Project,
        world_info_id: str,
        existing: dict[str, ProjectImportBinding],
        existing_world_uids: dict[str, int],
        existing_document_flags: dict[tuple[str, str], dict[str, bool]],
    ) -> None:
        self.project = project
        self.world_info_id = world_info_id
        self.existing = existing
        self.existing_world_uids = existing_world_uids
        self.existing_document_flags = existing_document_flags
        self.used_world_uids = set(existing_world_uids.values())
        self.next_world_uid = max(self.used_world_uids, default=0) + 1
        self.files: dict[str, str | bytes] = {}
        self.documents: list[dict[str, Any]] = []
        self.categories: list[dict[str, Any]] = []
        self.folders: list[dict[str, Any]] = []
        self.specs: dict[str, MappedBindingSpec] = {}
        self.target_owners: dict[tuple[str, str], str] = {}
        self.category_ids: dict[tuple[str, tuple[str, ...]], str] = {}
        self.category_sibling_orders: dict[tuple[str, tuple[str, ...]], int] = {}
        self.folder_ids: dict[tuple[str, str], str] = {}

    def world_uid_for(self, item: MappedSourceItem) -> int:
        _, target_id, _ = self.resolve(
            rule_id=item.rule_id,
            source_path=item.source,
            source_anchor=item.anchor,
            target_kind="world_entry",
            target_id_hint=item.target_id,
        )
        current_uid = self.existing_world_uids.get(target_id)
        if current_uid is not None:
            return current_uid
        while self.next_world_uid in self.used_world_uids:
            self.next_world_uid += 1
        uid = self.next_world_uid
        self.used_world_uids.add(uid)
        self.next_world_uid += 1
        return uid

    def resolve(
        self,
        *,
        rule_id: str,
        source_path: str,
        source_anchor: str,
        target_kind: str,
        target_id_hint: str | None = None,
    ) -> tuple[str, str, ProjectImportBinding | None]:
        key = _identity_key(self.project.id, rule_id, source_path, source_anchor, target_kind)
        binding = self.existing.get(key)
        if binding is not None and not _binding_metadata_matches(
            binding,
            rule_id=rule_id,
            source_path=source_path,
            source_anchor=source_anchor,
            target_kind=target_kind,
        ):
            raise BundleFormatError("stored import binding identity is inconsistent")
        if binding is not None and (
            target_id_hint is not None and binding.target_id != target_id_hint
        ):
            raise BundleFormatError("stored import target differs from source hint")
        target_id = binding.target_id if binding is not None else target_id_hint
        target_id = target_id or _generated_id(target_kind, key)
        if _TARGET_ID.fullmatch(target_id) is None:
            raise BundleFormatError("stored import target id is invalid")
        owner_key = (target_kind, target_id)
        previous_owner = self.target_owners.get(owner_key)
        if previous_owner is not None and previous_owner != key:
            raise BundleFormatError("mapped targets contain an id collision")
        self.target_owners[owner_key] = key
        return key, target_id, binding

    def record(
        self,
        *,
        key: str,
        rule_id: str,
        source_path: str,
        source_anchor: str,
        target_kind: str,
        target_id: str,
        incoming_hash: str,
    ) -> MappedBindingSpec:
        spec = MappedBindingSpec(
            key,
            rule_id,
            source_path,
            source_anchor,
            target_kind,
            target_id,
            incoming_hash,
        )
        previous = self.specs.get(key)
        if previous is not None and previous != spec:
            raise BundleFormatError("mapped binding has inconsistent semantics")
        self.specs[key] = spec
        return spec

    def folder_anchor(
        self, rule_id: str, scope: str, title: str, target_id_hint: str | None
    ) -> str:
        if target_id_hint:
            # Keep established source identities when accepting old exported mappings.
            bindings = [
                binding
                for binding in self.existing.values()
                if binding.rule_id == rule_id and binding.target_id == target_id_hint
            ]
            if len(bindings) > 1:
                raise BundleFormatError("folder ID has multiple source bindings")
            if bindings:
                return bindings[0].source_anchor
            return f"{scope}/@{target_id_hint}"
        return f"{scope}/{title}"

    def add_category_path(
        self,
        path: list[str],
        document_type: str,
        target_id_hints: list[str] | None = None,
        order_hints: list[int] | None = None,
        description: str | None = None,
        include_description: bool = False,
    ) -> str | None:
        if target_id_hints and len(target_id_hints) != len(path):
            raise BundleFormatError("category target hints do not match category path")
        if order_hints and len(order_hints) != len(path):
            raise BundleFormatError("category order hints do not match category path")
        if len(path) > 1:
            raise BundleFormatError("folder path cannot exceed one level")
        parent_id: str | None = None
        for depth in range(1, len(path) + 1):
            current_path = tuple(path[:depth])
            target_hint = target_id_hints[depth - 1] if target_id_hints else None
            category_key = (document_type, (target_hint,) if target_hint else current_path)
            existing_id = self.category_ids.get(category_key)
            if existing_id is not None:
                parent_id = existing_id
                continue
            anchor = self.folder_anchor(
                _CATEGORY_RULE_ID, document_type, current_path[-1], target_hint
            )
            key, category_id, binding = self.resolve(
                rule_id=_CATEGORY_RULE_ID,
                source_path="",
                source_anchor=anchor,
                target_kind="note_category",
                target_id_hint=(target_id_hints or [])[depth - 1] if target_id_hints else None,
            )
            parent_path = (document_type, current_path[:-1])
            next_order = self.category_sibling_orders.get(parent_path, 0)
            order = order_hints[depth - 1] if order_hints else next_order
            self.category_sibling_orders[parent_path] = max(next_order, order + 1)
            fields = {
                "kind": "note_category",
                "id": category_id,
                "project_id": self.project.id,
                "parent_id": parent_id,
                "title": current_path[-1],
                "document_type": document_type,
                "order": order,
                **(
                    {"description": description}
                    if description is not None or include_description
                    else {}
                ),
            }
            incoming_hash = semantic_hash(fields)
            self.categories.append(
                {
                    "id": category_id,
                    "project_id": self.project.id,
                    "parent_id": parent_id,
                    "title": current_path[-1],
                    "document_type": document_type,
                    "order": order,
                    **(
                        {"description": description}
                        if description is not None or include_description
                        else {}
                    ),
                    "base_hash": _base_hash(binding, incoming_hash),
                }
            )
            self.record(
                key=key,
                rule_id=_CATEGORY_RULE_ID,
                source_path="",
                source_anchor=anchor,
                target_kind="note_category",
                target_id=category_id,
                incoming_hash=incoming_hash,
            )
            self.category_ids[category_key] = category_id
            parent_id = category_id
        return parent_id

    def add_project_folder(
        self,
        path: list[str],
        scope: str,
        target_id_hints: list[str] | None = None,
        order_hints: list[int] | None = None,
        description: str | None = None,
        include_description: bool = False,
    ) -> str | None:
        if not path:
            return None
        if len(path) != 1:
            raise BundleFormatError("folder path cannot exceed one level")
        title = path[0]
        target_id_hint = target_id_hints[0] if target_id_hints else None
        folder_key = (scope, target_id_hint or title)
        if folder_key in self.folder_ids:
            return self.folder_ids[folder_key]
        target_id_hint = target_id_hints[0] if target_id_hints else None
        order = order_hints[0] if order_hints else sum(key[0] == scope for key in self.folder_ids)
        anchor = self.folder_anchor(_FOLDER_RULE_ID, scope, title, target_id_hint)
        key, folder_id, binding = self.resolve(
            rule_id=_FOLDER_RULE_ID,
            source_path="",
            source_anchor=anchor,
            target_kind="project_folder",
            target_id_hint=target_id_hint,
        )
        fields = {
            "kind": "project_folder",
            "id": folder_id,
            "project_id": self.project.id,
            "scope": scope,
            "title": title,
            "order": order,
            **(
                {"description": description}
                if description is not None or include_description
                else {}
            ),
        }
        incoming_hash = semantic_hash(fields)
        self.folders.append({**fields, "base_hash": _base_hash(binding, incoming_hash)})
        self.record(
            key=key,
            rule_id=_FOLDER_RULE_ID,
            source_path="",
            source_anchor=anchor,
            target_kind="project_folder",
            target_id=folder_id,
            incoming_hash=incoming_hash,
        )
        self.folder_ids[folder_key] = folder_id
        return folder_id

    def add_document(
        self,
        *,
        item: MappedSourceItem,
        target_kind: str,
        fields: dict[str, Any],
        title: str,
        body: str,
        path: str,
        anchor_suffix: str = "",
    ) -> str:
        source_anchor = item.anchor + anchor_suffix
        key, target_id, binding = self.resolve(
            rule_id=item.rule_id,
            source_path=item.source,
            source_anchor=source_anchor,
            target_kind=target_kind,
            target_id_hint=item.target_id,
        )
        complete_fields = {
            "kind": target_kind,
            "id": target_id,
            "project_id": self.project.id,
            **fields,
            **self.existing_document_flags.get((target_kind, target_id), {}),
            **{
                flag: item.metadata[flag]
                for flag in ("is_locked", "is_favorited")
                if flag in item.metadata
            },
        }
        incoming_hash = document_semantic_hash(complete_fields, title, body)
        base_hash = _base_hash(binding, incoming_hash)
        rendered_path = path.format(id=target_id)
        if rendered_path in self.files:
            raise BundleFormatError("mapped documents contain a path collision")
        self.files[rendered_path] = render_markdown_document(
            {
                "schema": "openfic.document",
                "version": 1,
                **complete_fields,
                "base_hash": base_hash,
            },
            title,
            body,
        )
        self.documents.append(
            {
                "kind": target_kind,
                "id": target_id,
                "path": rendered_path,
                "base_hash": base_hash,
            }
        )
        self.record(
            key=key,
            rule_id=item.rule_id,
            source_path=item.source,
            source_anchor=source_anchor,
            target_kind=target_kind,
            target_id=target_id,
            incoming_hash=incoming_hash,
        )
        return target_id

    def finish(self, source_items: list[MappedSourceItem]) -> MappedProjectBundle:
        manifest = {
            "schema": "openfic.project-bundle",
            "version": 1,
            "project": {
                "id": self.project.id,
                "title": self.project.title,
                "description": self.project.description or "",
            },
            "documents": sorted(self.documents, key=lambda item: item["path"]),
            "note_categories": self.categories,
            "project_folders": self.folders,
        }
        self.files["openfic.yaml"] = _yaml(manifest)
        return MappedProjectBundle(build_zip(self.files), source_items, list(self.specs.values()))


async def build_mapped_project_bundle(
    session: AsyncSession,
    target_project_id: str,
    source_data: bytes,
) -> MappedProjectBundle:
    project = await session.get(Project, target_project_id)
    if project is None:
        raise NotFoundError(f"项目不存在：{target_project_id}")
    source_items = parse_source_mapping(source_data, target_project_id)
    bindings = list(
        (
            await session.execute(
                select(ProjectImportBinding).where(
                    col(ProjectImportBinding.project_id) == target_project_id
                )
            )
        ).scalars()
    )
    existing = {binding.binding_key: binding for binding in bindings}
    world = (
        await session.execute(
            select(WorldInfo).where(col(WorldInfo.project_id) == target_project_id)
        )
    ).scalar_one_or_none()
    world_info_id = (
        world.id
        if world is not None
        else f"map-world-{hashlib.sha256(target_project_id.encode()).hexdigest()[:24]}"
    )
    existing_world_entries = list(
        (
            await session.execute(
                select(WorldInfoEntry).where(col(WorldInfoEntry.world_info_id) == world_info_id)
            )
        ).scalars()
    )
    existing_document_flags = {}
    for model, kind, flag in (
        (Character, "character", "is_favorited"),
        (Note, "note", "is_locked"),
    ):
        rows = (
            await session.execute(select(model).where(col(model.project_id) == target_project_id))
        ).scalars()
        existing_document_flags.update({(kind, row.id): {flag: getattr(row, flag)} for row in rows})
    builder = _Builder(
        project=project,
        world_info_id=world_info_id,
        existing=existing,
        existing_world_uids={entry.id: entry.uid for entry in existing_world_entries},
        existing_document_flags=existing_document_flags,
    )

    config, _ = read_source_mapping_manifest(source_data, target_project_id)
    _, source_folders = _source_metadata(config)
    for folder in source_folders.values():
        if folder["scope"] in {"note", "outline"}:
            builder.add_category_path(
                [folder["title"]],
                folder["scope"],
                [folder["id"]],
                [folder["order"]],
                folder.get("description"),
                include_description="description" in folder,
            )
        else:
            builder.add_project_folder(
                [folder["title"]],
                folder["scope"],
                [folder["id"]],
                [folder["order"]],
                folder.get("description"),
                include_description="description" in folder,
            )
    for item in source_items:
        slug = slugify_filename(item.title, item.rule_id)
        if item.target == "worldbook":
            folder_id = builder.add_project_folder(
                item.category_path,
                "world",
                item.category_target_ids,
                item.category_orders,
            )
            builder.add_document(
                item=item,
                target_kind="world_entry",
                fields={
                    "world_info_id": world_info_id,
                    "uid": builder.world_uid_for(item),
                    "section": item.section or "",
                    "order": item.order,
                    "agent_visibility": item.agent_visibility,
                    "folder_id": folder_id,
                },
                title=item.title,
                body=item.body,
                path=f"worldbook/{item.order:06d}-{slug}--{{id}}.md",
            )
        elif item.target == "characters":
            folder_id = builder.add_project_folder(
                item.category_path,
                "character",
                item.category_target_ids,
                item.category_orders,
            )
            builder.add_document(
                item=item,
                target_kind="character",
                fields={
                    "order": item.order,
                    "agent_visibility": item.agent_visibility,
                    "is_favorited": False,
                    "folder_id": folder_id,
                },
                title=item.title,
                body=item.body,
                path=f"characters/{item.order:06d}-{slug}--{{id}}.md",
            )
        elif item.target in {"notes", "outlines"}:
            document_type = "outline" if item.target == "outlines" else "note"
            category_id = builder.add_category_path(
                item.category_path,
                document_type,
                item.category_target_ids,
                item.category_orders,
            )
            builder.add_document(
                item=item,
                target_kind="note",
                fields={
                    "category_id": category_id,
                    "document_type": document_type,
                    "order": item.order,
                    "agent_visibility": item.agent_visibility,
                    "is_locked": False,
                },
                title=item.title,
                body=item.body,
                path=(f"{item.target}/_mapped/{item.order:06d}-{slug}--{{id}}.md"),
            )
    return builder.finish(source_items)


async def persist_mapped_import_bindings(
    session: AsyncSession,
    project_id: str,
    specs: list[MappedBindingSpec],
) -> None:
    current_rows = list(
        (
            await session.execute(
                select(ProjectImportBinding).where(
                    col(ProjectImportBinding.project_id) == project_id
                )
            )
        ).scalars()
    )
    current = {row.binding_key: row for row in current_rows}
    now = datetime.now(UTC)
    for spec in specs:
        row = current.get(spec.binding_key)
        if row is None:
            session.add(
                ProjectImportBinding(
                    project_id=project_id,
                    binding_key=spec.binding_key,
                    rule_id=spec.rule_id,
                    source_path=spec.source_path,
                    source_anchor=spec.source_anchor,
                    target_kind=spec.target_kind,
                    target_id=spec.target_id,
                    last_applied_hash=spec.incoming_hash,
                    created_at=now,
                    updated_at=now,
                )
            )
            continue
        if (
            not _binding_metadata_matches(
                row,
                rule_id=spec.rule_id,
                source_path=spec.source_path,
                source_anchor=spec.source_anchor,
                target_kind=spec.target_kind,
            )
            or row.target_id != spec.target_id
        ):
            raise BundleFormatError("stored import binding changed during apply")
        row.last_applied_hash = spec.incoming_hash
        row.updated_at = now
        session.add(row)
    await session.flush()


async def persist_source_mapping_profile(
    session: AsyncSession,
    project_id: str,
    mapping_yaml: str,
) -> None:
    """Save the source map only after its corresponding import was applied."""

    now = datetime.now(UTC)
    profile = await session.get(ProjectImportProfile, project_id)
    if profile is None:
        session.add(
            ProjectImportProfile(
                project_id=project_id,
                mapping_yaml=mapping_yaml,
                created_at=now,
                updated_at=now,
            )
        )
    else:
        profile.mapping_yaml = mapping_yaml
        profile.updated_at = now
        session.add(profile)
    await session.flush()
