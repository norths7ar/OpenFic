"""Version 2 source mapping: roots select types, directories select folders."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from app.core.agent_visibility import DEFAULT_AGENT_VISIBILITY, validate_agent_visibility

from .archive import BundleFormatError
from .item_markers import parse_items
from .source_mapping import MappedSourceItem, _source_metadata

TARGET_SCOPES = {
    "worldbook": "world",
    "characters": "character",
    "chapters": "writing",
    "notes": "note",
    "outlines": "outline",
}


def directory_rules(config: dict[str, Any]) -> list[dict[str, Any]]:
    rules = config.get("rules")
    if not isinstance(rules, list) or not rules:
        raise BundleFormatError("directory rules must be non-empty")
    ids, roots = set(), []
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) - {
            "id",
            "source",
            "target",
            "layout",
            "required",
        }:
            raise BundleFormatError("directory rule fields are invalid")
        root = rule.get("source")
        if (
            not isinstance(root, str)
            or not root
            or "\\" in root
            or ":" in root
            or root.startswith("/")
            or any(part in {"", ".", ".."} for part in root.split("/"))
        ):
            raise BundleFormatError("directory rule source must be a relative directory")
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id or rule_id in ids:
            raise BundleFormatError("directory rule id is missing or duplicated")
        if rule.get("target") not in TARGET_SCOPES:
            raise BundleFormatError("directory rule target is invalid")
        if rule.get("layout", "files") not in {"files", "merged"}:
            raise BundleFormatError("directory rule layout must be files or merged")
        if "required" in rule and not isinstance(rule["required"], bool):
            raise BundleFormatError("directory rule required must be boolean")
        if any(
            root == other or root.startswith(other + "/") or other.startswith(root + "/")
            for other in roots
        ):
            raise BundleFormatError("directory mapping roots must not overlap")
        ids.add(rule_id)
        roots.append(root)
    return rules


def parse_directory_mapping(
    files: dict[str, bytes], config: dict[str, Any]
) -> list[MappedSourceItem]:
    rules = directory_rules(config)
    if config.get("items"):
        raise BundleFormatError("version 2 item metadata belongs in openfic:item markers")
    _, folders = _source_metadata(config)
    folder_paths = {}
    for folder in folders.values():
        path = folder.get("source")
        matches = [
            rule
            for rule in rules
            if isinstance(path, str) and path.startswith(rule["source"] + "/")
        ]
        if not isinstance(path, str) or len(matches) != 1:
            raise BundleFormatError("folder source must belong to one mapped directory")
        rule = matches[0]
        relative = path[len(rule["source"]) + 1 :]
        if not relative or "/" in relative or "\\" in relative or relative in {".", ".."}:
            raise BundleFormatError("only one folder level is supported")
        if folder["scope"] != TARGET_SCOPES[rule["target"]] or path in folder_paths:
            raise BundleFormatError("folder source scope is invalid or duplicated")
        folder_paths[path] = folder
    output, identities = [], set()
    for rule in rules:
        root = PurePosixPath(rule["source"])
        matches = sorted(
            path for path in files if path.startswith(str(root) + "/") and path.endswith(".md")
        )
        if not matches and rule.get("required", False):
            raise BundleFormatError("directory rule has no matching files")
        for path in matches:
            relative = PurePosixPath(path).relative_to(root)
            if len(relative.parts) > 2:
                raise BundleFormatError("only one folder level is supported")
            folder = folder_paths.get(str(PurePosixPath(path).parent))
            folder_title = (
                folder["title"]
                if folder
                else (relative.parts[0] if len(relative.parts) == 2 else None)
            )
            try:
                items = parse_items(files[path].decode("utf-8"))
            except UnicodeDecodeError as exc:
                raise BundleFormatError("source file must be UTF-8") from exc
            for metadata, body in items:
                kind = "note" if rule["target"] in {"notes", "outlines"} else rule["target"]
                identity = (kind, metadata["id"])
                if identity in identities:
                    raise BundleFormatError("source items contain duplicate target IDs")
                identities.add(identity)
                if (
                    ("section" in metadata and rule["target"] != "worldbook")
                    or ("is_locked" in metadata and rule["target"] not in {"notes", "outlines"})
                    or ("is_favorited" in metadata and rule["target"] != "characters")
                ):
                    raise BundleFormatError("source item metadata fields differ from target")
                try:
                    visible = validate_agent_visibility(
                        metadata.get("agent_visibility", DEFAULT_AGENT_VISIBILITY)
                    )
                except ValueError as exc:
                    raise BundleFormatError("source item visibility is invalid") from exc
                output.append(
                    MappedSourceItem(
                        source=path,
                        rule_id=rule["id"],
                        target=rule["target"],
                        anchor="item:" + metadata["id"],
                        title=metadata["title"],
                        body=body,
                        section=metadata.get("section"),
                        category_path=[folder_title] if folder_title else [],
                        agent_visibility=visible,
                        order=metadata.get("order", len(output)),
                        target_id=metadata["id"],
                        category_target_ids=[folder["id"]] if folder else [],
                        category_orders=[folder["order"]] if folder else [],
                        metadata=metadata,
                    )
                )
    return output
