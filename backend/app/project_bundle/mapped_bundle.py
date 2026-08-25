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
from app.project_bundle.source_mapping import MappedSourceItem, parse_source_mapping
from app.storage.models.project import Project
from app.storage.models.project_import_binding import ProjectImportBinding
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC).isoformat()
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_TARGET_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CATEGORY_RULE_ID = "__mapped_categories__"


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
        "discussion": "map-di",
        "discussion_message": "map-dm",
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
    ) -> None:
        self.project = project
        self.world_info_id = world_info_id
        self.existing = existing
        self.existing_world_uids = existing_world_uids
        self.used_world_uids = set(existing_world_uids.values())
        self.next_world_uid = max(self.used_world_uids, default=0) + 1
        self.files: dict[str, str | bytes] = {}
        self.documents: list[dict[str, Any]] = []
        self.categories: list[dict[str, Any]] = []
        self.specs: dict[str, MappedBindingSpec] = {}
        self.target_owners: dict[tuple[str, str], str] = {}
        self.category_ids: dict[tuple[str, ...], str] = {}
        self.category_sibling_orders: dict[tuple[str, ...], int] = {}

    def world_uid_for(self, item: MappedSourceItem) -> int:
        _, target_id, _ = self.resolve(
            rule_id=item.rule_id,
            source_path=item.source,
            source_anchor=item.anchor,
            target_kind="world_entry",
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
    ) -> tuple[str, str, ProjectImportBinding | None]:
        key = _identity_key(
            self.project.id, rule_id, source_path, source_anchor, target_kind
        )
        binding = self.existing.get(key)
        if binding is not None and not _binding_metadata_matches(
            binding,
            rule_id=rule_id,
            source_path=source_path,
            source_anchor=source_anchor,
            target_kind=target_kind,
        ):
            raise BundleFormatError("stored import binding identity is inconsistent")
        target_id = (
            binding.target_id
            if binding is not None
            else _generated_id(target_kind, key)
        )
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

    def add_category_path(self, path: list[str]) -> str | None:
        parent_id: str | None = None
        for depth in range(1, len(path) + 1):
            current_path = tuple(path[:depth])
            existing_id = self.category_ids.get(current_path)
            if existing_id is not None:
                parent_id = existing_id
                continue
            anchor = "/".join(current_path)
            key, category_id, binding = self.resolve(
                rule_id=_CATEGORY_RULE_ID,
                source_path="",
                source_anchor=anchor,
                target_kind="note_category",
            )
            parent_path = current_path[:-1]
            order = self.category_sibling_orders.get(parent_path, 0)
            self.category_sibling_orders[parent_path] = order + 1
            fields = {
                "kind": "note_category",
                "id": category_id,
                "project_id": self.project.id,
                "parent_id": parent_id,
                "title": current_path[-1],
                "order": order,
            }
            incoming_hash = semantic_hash(fields)
            self.categories.append(
                {
                    "id": category_id,
                    "project_id": self.project.id,
                    "parent_id": parent_id,
                    "title": current_path[-1],
                    "order": order,
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
            self.category_ids[current_path] = category_id
            parent_id = category_id
        return parent_id

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
        )
        complete_fields = {
            "kind": target_kind,
            "id": target_id,
            "project_id": self.project.id,
            **fields,
        }
        hash_fields = complete_fields
        if target_kind == "discussion_message":
            hash_fields = {
                key: value
                for key, value in complete_fields.items()
                if key not in {"created_at", "updated_at"}
            }
        incoming_hash = document_semantic_hash(hash_fields, title, body)
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
        }
        self.files["openfic.yaml"] = _yaml(manifest)
        return MappedProjectBundle(
            build_zip(self.files), source_items, list(self.specs.values())
        )


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
                select(WorldInfoEntry).where(
                    col(WorldInfoEntry.world_info_id) == world_info_id
                )
            )
        ).scalars()
    )
    builder = _Builder(
        project=project,
        world_info_id=world_info_id,
        existing=existing,
        existing_world_uids={entry.id: entry.uid for entry in existing_world_entries},
    )

    discussion_index = 0
    for item in source_items:
        slug = slugify_filename(item.title, item.rule_id)
        if item.target == "worldbook":
            builder.add_document(
                item=item,
                target_kind="world_entry",
                fields={
                    "world_info_id": world_info_id,
                    "uid": builder.world_uid_for(item),
                    "section": item.section or "",
                    "order": item.order,
                    "writing_visible": item.writing_visible,
                },
                title=item.title,
                body=item.body,
                path=f"worldbook/{item.order:06d}-{slug}--{{id}}.md",
            )
        elif item.target == "characters":
            builder.add_document(
                item=item,
                target_kind="character",
                fields={
                    "order": item.order,
                    "writing_visible": item.writing_visible,
                    "is_favorited": False,
                },
                title=item.title,
                body=item.body,
                path=f"characters/{item.order:06d}-{slug}--{{id}}.md",
            )
        elif item.target == "notes":
            category_id = builder.add_category_path(item.category_path)
            builder.add_document(
                item=item,
                target_kind="note",
                fields={
                    "category_id": category_id,
                    "order": item.order,
                    "writing_visible": item.writing_visible,
                    "is_locked": False,
                    "is_hidden": False,
                },
                title=item.title,
                body=item.body,
                path=f"notes/_mapped/{item.order:06d}-{slug}--{{id}}.md",
            )
        else:
            discussion_index += 1
            directory = f"discussions/{discussion_index:06d}-{slug}--{{id}}"
            discussion_id = builder.add_document(
                item=item,
                target_kind="discussion",
                fields={"context_mode": item.context_mode or "global"},
                title=item.title,
                body="",
                path=f"{directory}/discussion.md",
            )
            if item.body:
                message_directory = (
                    f"discussions/{discussion_index:06d}-{slug}--{discussion_id}"
                )
                builder.add_document(
                    item=item,
                    target_kind="discussion_message",
                    fields={
                        "discussion_id": discussion_id,
                        "seq": 0,
                        "role": "assistant",
                        "status": "completed",
                        "created_at": _EPOCH,
                        "updated_at": _EPOCH,
                    },
                    title="助手 000000",
                    body=item.body,
                    path=(f"{message_directory}/messages/000000-assistant--{{id}}.md"),
                    anchor_suffix="/message:0",
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
