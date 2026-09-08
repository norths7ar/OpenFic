"""Pure, declarative Markdown source mapping for future bundle imports."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field, replace
from typing import Any, NoReturn

import yaml

from app.core.agent_visibility import (
    AGENT_VISIBILITY_STATES,
    DEFAULT_AGENT_VISIBILITY,
    AgentVisibility,
    validate_agent_visibility,
)

from .archive import BundleFormatError, read_zip
from .markdown import restore_body_format


@dataclass(frozen=True)
class MappedSourceItem:
    source: str
    rule_id: str
    target: str
    anchor: str
    title: str
    body: str
    section: str | None
    category_path: list[str]
    agent_visibility: AgentVisibility
    order: int
    target_id: str | None
    category_target_ids: list[str]
    category_orders: list[int]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _Heading:
    line: int
    level: int
    title: str
    ancestors: tuple[_Heading, ...] = ()


_TARGETS = {"worldbook", "characters", "chapters", "notes", "outlines"}
_RULE_KEYS = {
    "id",
    "target",
    "source",
    "glob",
    "split",
    "section_level",
    "category_levels",
    "category_path",
    "folder_level",
    "folder_path",
    "folder_target_id",
    "folder_order",
    "agent_visibility",
    "required",
    "target_id",
    "category_target_ids",
    "order",
    "order_step",
    "category_orders",
}
_SPLIT_KEYS = {"type", "item_levels"}
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*$")
_TARGET_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CHAPTER_FILE_KEYS = {"id", "volume_id", "order"}


def _fail(message: str) -> NoReturn:
    raise BundleFormatError(message)


def _int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{name} must be an integer")
    return value


def _scan(text: str) -> list[_Heading]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    headings: list[_Heading] = []
    stack: list[_Heading] = []
    fence_char, fence_length = "", 0
    for index, line in enumerate(lines):
        if fence_char:
            closing = re.match(
                rf"^ {{0,3}}{re.escape(fence_char)}{{{fence_length},}}[ \t]*$",
                line,
            )
            if closing:
                fence_char, fence_length = "", 0
            continue
        fence = _FENCE.match(line)
        if fence:
            marker = fence.group(1)
            fence_char, fence_length = marker[0], len(marker)
            continue
        match = _HEADING.match(line)
        if not match:
            continue
        title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2)).strip()
        if not title:
            _fail("heading title must not be empty")
        level = len(match.group(1))
        if headings and level > headings[-1].level + 1:
            _fail("heading levels must not jump")
        while stack and stack[-1].level >= level:
            stack.pop()
        heading = _Heading(index, level, title, tuple(stack))
        headings.append(heading)
        stack.append(heading)
    if sum(heading.level == 1 for heading in headings) != 1:
        _fail("each source file must contain exactly one H1")
    return headings


def _chapter_file_metadata(text: str) -> dict[str, Any]:
    """Read the identity envelope required by every mapped chapter file."""

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines or lines[0] != "---":
        _fail("chapter source must begin with OpenFic chapter metadata")
    try:
        closing = lines.index("---", 1)
    except ValueError:
        _fail("chapter source metadata is not terminated")
    try:
        parsed = yaml.safe_load("\n".join(lines[1:closing]))
    except yaml.YAMLError as exc:
        raise BundleFormatError("chapter source metadata is invalid YAML") from exc
    if not isinstance(parsed, dict) or set(parsed) != {"openfic_chapter"}:
        _fail("chapter source metadata must contain only openfic_chapter")
    chapter = parsed["openfic_chapter"]
    if not isinstance(chapter, dict) or set(chapter) != _CHAPTER_FILE_KEYS:
        _fail("chapter source metadata fields are invalid")
    chapter_id = chapter.get("id")
    volume_id = chapter.get("volume_id")
    if not isinstance(chapter_id, str) or _TARGET_ID.fullmatch(chapter_id) is None:
        _fail("chapter source id is invalid")
    if volume_id is not None and (
        not isinstance(volume_id, str) or _TARGET_ID.fullmatch(volume_id) is None
    ):
        _fail("chapter source volume_id is invalid")
    order = _int(chapter.get("order"), "chapter source order")
    if order < 0:
        _fail("chapter source order must be non-negative")
    return {"id": chapter_id, "volume_id": volume_id, "order": order}


def _validate_rule(rule: Any) -> dict[str, Any]:
    if not isinstance(rule, dict):
        _fail("each rule must be a mapping")
    unknown = set(rule) - _RULE_KEYS
    if unknown:
        _fail(f"unknown rule fields: {sorted(unknown)}")
    rule_id, target = rule.get("id"), rule.get("target")
    if not isinstance(rule_id, str) or not rule_id:
        _fail("rule id must be non-empty")
    if target not in _TARGETS:
        _fail("rule target is invalid")
    has_source = isinstance(rule.get("source"), str) and bool(rule["source"])
    has_glob = isinstance(rule.get("glob"), str) and bool(rule["glob"])
    if has_source == has_glob:
        _fail("rule must have exactly one non-empty source or glob")
    split = rule.get("split")
    if not isinstance(split, dict) or set(split) - _SPLIT_KEYS:
        _fail("split must be a mapping with known fields")
    split_type = split.get("type")
    if split_type not in {"file", "headings"}:
        _fail("split type must be file or headings")
    if target == "chapters" and split_type != "file":
        _fail("chapters must use one file per chapter")
    levels = split.get("item_levels")
    if split_type == "headings":
        if not isinstance(levels, list) or not levels:
            _fail("headings split requires item_levels")
        parsed = [_int(level, "item level") for level in levels]
        if parsed != sorted(set(parsed)) or any(level < 2 or level > 6 for level in parsed):
            _fail("item_levels must be unique, ascending, and between 2 and 6")
    elif "item_levels" in split:
        _fail("file split cannot have item_levels")
    if split_type == "file" and any(
        key in rule for key in ("section_level", "category_levels", "folder_level")
    ):
        _fail("folder_level requires headings split")
    if "folder_level" in rule and any(key in rule for key in ("section_level", "category_levels")):
        _fail("folder_level cannot be combined with legacy hierarchy fields")
    if "folder_path" in rule and "category_path" in rule:
        _fail("folder_path cannot be combined with legacy category_path")
    if "folder_level" in rule:
        folder_level = _int(rule["folder_level"], "folder_level")
        if folder_level < 1 or folder_level >= min(levels):
            _fail("folder_level must be below all item levels")
    if "section_level" in rule:
        if target != "worldbook":
            _fail("section_level is only valid for worldbook")
        section_level = _int(rule["section_level"], "section_level")
        if section_level < 1 or section_level >= min(levels):
            _fail("section_level must be below all item levels")
    if "category_levels" in rule:
        if target not in {"chapters", "notes", "outlines"} or not isinstance(
            rule["category_levels"], list
        ):
            _fail("category_levels is only valid as a list for notes or outlines")
        category_levels = [_int(level, "category_levels") for level in rule["category_levels"]]
        if (
            category_levels != sorted(set(category_levels))
            or any(level < 2 or level > 6 for level in category_levels)
            or any(level >= max(levels) for level in category_levels)
            or len(category_levels) > 1
        ):
            _fail("category_levels must contain at most one ancestor level")
    if "category_path" in rule and (
        target not in {"chapters", "notes", "outlines"}
        or not isinstance(rule["category_path"], list)
        or any(not isinstance(value, str) or not value for value in rule["category_path"])
    ):
        _fail("category_path must be a list of non-empty strings for notes or outlines")
    if "folder_path" in rule and (
        not isinstance(rule["folder_path"], list)
        or len(rule["folder_path"]) > 1
        or any(not isinstance(value, str) or not value for value in rule["folder_path"])
    ):
        _fail("folder_path must contain at most one non-empty string")
    if "agent_visibility" in rule:
        try:
            validate_agent_visibility(rule["agent_visibility"])
        except ValueError as exc:
            raise BundleFormatError("agent_visibility is invalid") from exc
    if "required" in rule and not isinstance(rule["required"], bool):
        _fail("required must be a boolean")
    if "target_id" in rule and (
        split_type != "file"
        or not has_source
        or not isinstance(rule["target_id"], str)
        or _TARGET_ID.fullmatch(rule["target_id"]) is None
    ):
        _fail("target_id is only valid for one file-split source")
    if "order" in rule and (not has_source or _int(rule["order"], "order") < 0):
        _fail("order is only valid as a non-negative single-source rule integer")
    if "order_step" in rule and (
        split_type != "headings"
        or "order" not in rule
        or _int(rule["order_step"], "order_step") <= 0
    ):
        _fail("order_step is only valid as a positive heading-rule integer with order")
    if "category_target_ids" in rule:
        category_ids = rule["category_target_ids"]
        category_path = rule.get("category_path")
        if (
            target not in {"chapters", "notes", "outlines"}
            or split_type != "file"
            or not has_source
            or not isinstance(category_ids, list)
            or not isinstance(category_path, list)
            or len(category_ids) != len(category_path)
            or any(
                not isinstance(value, str) or _TARGET_ID.fullmatch(value) is None
                for value in category_ids
            )
        ):
            _fail("category_target_ids must match a file rule category_path")
    if "category_orders" in rule:
        category_orders = rule["category_orders"]
        category_path = rule.get("category_path")
        if (
            target not in {"chapters", "notes", "outlines"}
            or split_type != "file"
            or not has_source
            or not isinstance(category_orders, list)
            or not isinstance(category_path, list)
            or len(category_orders) != len(category_path)
            or any(_int(value, "category order") < 0 for value in category_orders)
        ):
            _fail("category_orders must match a file rule category_path")
    if "folder_target_id" in rule and (
        split_type != "file"
        or not has_source
        or not isinstance(rule["folder_target_id"], str)
        or _TARGET_ID.fullmatch(rule["folder_target_id"]) is None
        or not rule.get("folder_path")
    ):
        _fail("folder_target_id requires a file rule with folder_path")
    if "folder_order" in rule and (
        split_type != "file"
        or not has_source
        or _int(rule["folder_order"], "folder_order") < 0
        or not rule.get("folder_path")
    ):
        _fail("folder_order requires a file rule with folder_path")
    return rule


def _mapped_items(path: str, text: str, rule: dict[str, Any]) -> list[MappedSourceItem]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    headings = _scan(text)
    target = rule["target"]
    chapter_metadata = _chapter_file_metadata(text) if target == "chapters" else None
    visible = validate_agent_visibility(rule.get("agent_visibility", DEFAULT_AGENT_VISIBILITY))
    h1 = next(heading for heading in headings if heading.level == 1)

    def item_title_and_visibility(title: str) -> tuple[str, AgentVisibility]:
        for state in sorted(
            AGENT_VISIBILITY_STATES, key=lambda state: len(state.export_marker), reverse=True
        ):
            suffix = state.export_marker
            if suffix and title.endswith(suffix):
                clean_title = title[: -len(suffix)].rstrip()
                if not clean_title:
                    _fail("visibility marker must not consume the whole title")
                return clean_title, state.value
        return title, visible

    def file_folder_metadata() -> tuple[list[str], list[str], list[int]]:
        folder_path = list(rule.get("folder_path", rule.get("category_path", [])))
        target_ids = (
            [rule["folder_target_id"]]
            if "folder_target_id" in rule
            else list(rule.get("category_target_ids", []))
        )
        orders = (
            [rule["folder_order"]]
            if "folder_order" in rule
            else list(rule.get("category_orders", []))
        )
        if len(folder_path) <= 1:
            return folder_path, target_ids, orders
        # Legacy maps could describe a category chain. Preserve its readable
        # identity while importing it as the single folder supported now.
        return [" / ".join(folder_path)], target_ids[-1:], orders[-1:]

    if rule["split"]["type"] == "file":
        title, item_visible = item_title_and_visibility(h1.title)
        folder_path, folder_target_ids, folder_orders = file_folder_metadata()
        if chapter_metadata is not None:
            if rule.get("target_id") not in {None, chapter_metadata["id"]}:
                _fail("chapter rule target_id conflicts with chapter metadata")
            if rule.get("order") not in {None, chapter_metadata["order"]}:
                _fail("chapter rule order conflicts with chapter metadata")
            if folder_path and chapter_metadata["volume_id"] is None:
                _fail("root chapter metadata conflicts with chapter rule folder")
            if folder_target_ids and folder_target_ids != [chapter_metadata["volume_id"]]:
                _fail("chapter rule folder conflicts with chapter metadata")
        return [
            MappedSourceItem(
                path,
                rule["id"],
                target,
                "H1:" + title,
                title,
                "\n".join(lines[h1.line + 1 :]).strip("\n"),
                None,
                folder_path,
                item_visible,
                chapter_metadata["order"]
                if chapter_metadata is not None
                else rule.get("order", -1),
                chapter_metadata["id"] if chapter_metadata is not None else rule.get("target_id"),
                (
                    [chapter_metadata["volume_id"]]
                    if chapter_metadata is not None and chapter_metadata["volume_id"] is not None
                    else folder_target_ids
                ),
                folder_orders,
                {"chapter_file": chapter_metadata} if chapter_metadata is not None else {},
            )
        ]
    item_levels = set(rule["split"]["item_levels"])
    selected = [heading for heading in headings if heading.level in item_levels]
    if not selected:
        _fail("headings split produced no items")
    results: list[MappedSourceItem] = []
    folder_level = rule.get("folder_level")
    section_level = rule.get("section_level")
    category_levels = set(rule.get("category_levels", []))
    configured_order = rule.get("order")
    order_step = rule.get("order_step", 1)
    for index, heading in enumerate(selected):
        title, item_visible = item_title_and_visibility(heading.title)
        end = len(lines)
        for candidate in headings:
            if candidate.line <= heading.line:
                continue
            if candidate.level <= heading.level or candidate.level in item_levels:
                end = candidate.line
                break
        ancestors = heading.ancestors
        section = next(
            (item.title for item in reversed(ancestors) if item.level == section_level),
            None,
        )
        categories = list(rule.get("folder_path", rule.get("category_path", [])))
        if folder_level is not None:
            dynamic_folders = [item.title for item in ancestors if item.level == folder_level]
            if dynamic_folders:
                categories = [dynamic_folders[-1]]
        elif target == "worldbook" and section is not None:
            categories = [section]
        else:
            dynamic_folders = [item.title for item in ancestors if item.level in category_levels]
            if dynamic_folders:
                categories = [dynamic_folders[-1]]
        if len(categories) > 1:
            categories = [" / ".join(categories)]
        anchor = "/".join(
            [
                *(
                    f"H{item.level}:{item_title_and_visibility(item.title)[0] if item.level in item_levels else item.title}"
                    for item in ancestors
                ),
                f"H{heading.level}:{title}",
            ]
        )
        results.append(
            MappedSourceItem(
                path,
                rule["id"],
                target,
                anchor,
                title,
                "\n".join(lines[heading.line + 1 : end]).strip("\n"),
                section,
                categories,
                item_visible,
                configured_order + index * order_step if configured_order is not None else -1,
                rule.get("target_id"),
                list(rule.get("category_target_ids", [])),
                list(rule.get("category_orders", [])),
            )
        )
    return results


def _read_source_mapping_manifest(
    files: dict[str, bytes], target_project_id: str
) -> tuple[dict[str, Any], str]:
    config_bytes = files.get("openfic-import.yaml")
    if config_bytes is None:
        _fail("openfic-import.yaml is required")
    assert isinstance(config_bytes, bytes)
    try:
        config = yaml.safe_load(config_bytes.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise BundleFormatError("openfic-import.yaml must be UTF-8 YAML") from exc
    if not isinstance(config, dict) or set(config) - {
        "schema",
        "version",
        "project_id",
        "rules",
        "items",
        "folders",
    }:
        _fail("invalid import map fields")
    configured_project_id = config.get("project_id")
    if (
        config.get("schema") != "openfic.import-map"
        or config.get("version") != 1
        or (configured_project_id is not None and configured_project_id != target_project_id)
    ):
        _fail("invalid import map identity")
    rules = config.get("rules")
    if not isinstance(rules, list) or not rules:
        _fail("rules must be non-empty")
    return config, config_bytes.decode("utf-8")


def _source_metadata(
    config: dict[str, Any],
) -> tuple[dict[tuple[str, str, str], dict[str, Any]], dict[str, dict[str, Any]]]:
    folders: dict[str, dict[str, Any]] = {}
    raw_folders = config.get("folders", [])
    raw_items = config.get("items", [])
    if not isinstance(raw_folders, list) or not isinstance(raw_items, list):
        _fail("source items and folders must be lists")
    for folder in raw_folders:
        if not isinstance(folder, dict) or set(folder) - {
            "id",
            "scope",
            "title",
            "order",
            "description",
        }:
            _fail("source folder metadata is invalid")
        if not isinstance(folder.get("id"), str) or not _TARGET_ID.fullmatch(folder["id"]):
            _fail("source folder id is invalid")
        if (
            folder["id"] in folders
            or not isinstance(folder.get("scope"), str)
            or folder["scope"]
            not in {
                "world",
                "character",
                "writing",
                "note",
                "outline",
            }
        ):
            _fail("source folder identity is invalid")
        if (
            not isinstance(folder.get("title"), str)
            or not folder["title"]
            or _int(folder.get("order"), "folder order") < 0
        ):
            _fail("source folder title/order is invalid")
        if folder.get("description") is not None and not isinstance(folder["description"], str):
            _fail("source folder description is invalid")
        folders[folder["id"]] = folder
    items: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in raw_items:
        if not isinstance(item, dict) or set(item) - {
            "rule_id",
            "source",
            "anchor",
            "target_id",
            "order",
            "section",
            "folder_id",
            "is_locked",
            "is_favorited",
            "body_format",
        }:
            _fail("source item metadata is invalid")
        if any(
            not isinstance(item.get(key), str) or not item[key]
            for key in ("rule_id", "source", "anchor", "target_id")
        ) or not _TARGET_ID.fullmatch(item["target_id"]):
            _fail("source item identity is invalid")
        key = (item["rule_id"], item["source"], item["anchor"])
        if key in items or _int(item.get("order"), "item order") < 0:
            _fail("duplicate source item metadata or invalid order")
        if (
            "folder_id" in item
            and item["folder_id"] is not None
            and (not isinstance(item["folder_id"], str) or item["folder_id"] not in folders)
        ):
            _fail("source item references a missing folder")
        if "section" in item and not isinstance(item["section"], str):
            _fail("source item section is invalid")
        for flag in ("is_locked", "is_favorited"):
            if flag in item and not isinstance(item[flag], bool):
                _fail("source item flag is invalid")
        if "body_format" in item:
            restore_body_format("", item["body_format"])
        items[key] = item
    return items, folders


def read_source_mapping_manifest(data: bytes, target_project_id: str) -> tuple[dict[str, Any], str]:
    return _read_source_mapping_manifest(read_zip(data), target_project_id)


def parse_source_mapping(data: bytes, target_project_id: str) -> list[MappedSourceItem]:
    files = read_zip(data)
    config, _ = _read_source_mapping_manifest(files, target_project_id)
    metadata, folders = _source_metadata(config)
    rules = config["rules"]
    seen_rules: set[str] = set()
    seen_logic: set[tuple[str, str, str]] = set()
    output: list[MappedSourceItem] = []
    orders: dict[str, int] = {}
    used_metadata: set[tuple[str, str, str]] = set()
    target_ids: set[tuple[str, str]] = set()
    for raw_rule in rules:
        rule = _validate_rule(raw_rule)
        if rule["id"] in seen_rules:
            _fail("duplicate rule id")
        seen_rules.add(rule["id"])
        if isinstance(rule.get("source"), str) and rule["source"]:
            matches = [rule["source"]] if rule["source"] in files else []
        else:
            matches = sorted(path for path in files if fnmatch.fnmatchcase(path, rule["glob"]))
        if not matches:
            if rule.get("required", True):
                _fail("source rule has no matching files")
            continue
        for path in matches:
            if (
                not isinstance(path, str)
                or path == "openfic-import.yaml"
                or not path.endswith(".md")
                or path not in files
            ):
                _fail("source rule matched an invalid file")
            try:
                text = files[path].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise BundleFormatError(f"source file is not UTF-8: {path}") from exc
            for item in _mapped_items(path, text, rule):
                chapter_file = item.metadata.get("chapter_file")
                if item.target == "chapters":
                    if not isinstance(chapter_file, dict):
                        _fail("chapter source metadata is missing")
                    volume_id = chapter_file["volume_id"]
                    folder = folders.get(volume_id) if volume_id is not None else None
                    if volume_id is not None and (folder is None or folder["scope"] != "writing"):
                        _fail("chapter source volume is missing or not a writing folder")
                    item = replace(
                        item,
                        category_path=[folder["title"]] if folder else [],
                        category_target_ids=[folder["id"]] if folder else [],
                        category_orders=[folder["order"]] if folder else [],
                    )
                details = (
                    None
                    if item.target == "chapters"
                    else metadata.get((item.rule_id, item.source, item.anchor))
                )
                metadata_key = (item.rule_id, item.source, item.anchor)
                # File-split rules carry a stable target_id. When users rename
                # that file or its H1, retain the recorded object identity and
                # let a successful apply refresh the stored source location.
                if item.target != "chapters" and details is None and item.target_id is not None:
                    candidates = [
                        (key, value)
                        for key, value in metadata.items()
                        if value["target_id"] == item.target_id and key[0] == item.rule_id
                    ]
                    if len(candidates) == 1:
                        metadata_key, details = candidates[0]
                if item.target == "chapters":
                    # Older source exports recorded chapter identity in the
                    # manifest.  A current file envelope is authoritative, but
                    # count that legacy entry as consumed if it still agrees.
                    candidates = [
                        (key, value)
                        for key, value in metadata.items()
                        if value["target_id"] == item.target_id and key[0] == item.rule_id
                    ]
                    if len(candidates) == 1:
                        used_metadata.add(candidates[0][0])
                if details is not None:
                    used_metadata.add(metadata_key)
                    if (
                        ("section" in details and item.target != "worldbook")
                        or ("is_favorited" in details and item.target != "characters")
                        or ("is_locked" in details and item.target not in {"notes", "outlines"})
                    ):
                        _fail("source item metadata fields differ from target")
                    folder = folders.get(details.get("folder_id"))
                    expected_scope = {
                        "worldbook": "world",
                        "characters": "character",
                        "notes": "note",
                        "outlines": "outline",
                        "chapters": "writing",
                    }[item.target]
                    if folder and folder["scope"] != expected_scope:
                        _fail("source item folder scope differs from target")
                    item = replace(
                        item,
                        target_id=details["target_id"],
                        order=details["order"],
                        section=details.get("section", item.section),
                        category_path=([folder["title"]] if folder else [])
                        if "folder_id" in details
                        else item.category_path,
                        category_target_ids=([folder["id"]] if folder else [])
                        if "folder_id" in details
                        else item.category_target_ids,
                        category_orders=([folder["order"]] if folder else [])
                        if "folder_id" in details
                        else item.category_orders,
                        body=restore_body_format(item.body, details["body_format"])
                        if "body_format" in details
                        else item.body,
                        metadata={**item.metadata, **details},
                    )
                logic = (item.target, item.source, item.anchor)
                if item.target_id is not None:
                    target_kind = (
                        "note"
                        if item.target in {"notes", "outlines"}
                        else ("chapter" if item.target == "chapters" else item.target)
                    )
                    identity = (target_kind, item.target_id)
                    if identity in target_ids:
                        _fail("source items contain duplicate target IDs")
                    target_ids.add(identity)
                if logic in seen_logic:
                    _fail("duplicate logical object")
                seen_logic.add(logic)
                next_order = orders.get(item.target, 0)
                order = item.order if item.order >= 0 else next_order
                output.append(replace(item, order=order))
                orders[item.target] = max(next_order, order + 1)
    if metadata.keys() - used_metadata:
        _fail(
            "source item metadata has unmatched anchors; update its source/anchor when moving or renaming headings"
        )
    return output
