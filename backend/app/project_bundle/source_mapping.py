"""Pure, declarative Markdown source mapping for future bundle imports."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, replace
from typing import Any

import yaml

from .archive import BundleFormatError, read_zip


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
    writing_visible: bool
    context_mode: str | None
    order: int


@dataclass(frozen=True)
class _Heading:
    line: int
    level: int
    title: str
    ancestors: tuple[_Heading, ...] = ()


_TARGETS = {"worldbook", "characters", "notes", "outlines", "discussions"}
_RULE_KEYS = {
    "id",
    "target",
    "source",
    "glob",
    "split",
    "section_level",
    "category_levels",
    "category_path",
    "writing_visible",
    "disabled_title_suffix",
    "context_mode",
}
_SPLIT_KEYS = {"type", "item_levels"}
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*$")


def _fail(message: str) -> None:
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
    levels = split.get("item_levels")
    if split_type == "headings":
        if not isinstance(levels, list) or not levels:
            _fail("headings split requires item_levels")
        parsed = [_int(level, "item level") for level in levels]
        if parsed != sorted(set(parsed)) or any(
            level < 2 or level > 6 for level in parsed
        ):
            _fail("item_levels must be unique, ascending, and between 2 and 6")
    elif "item_levels" in split:
        _fail("file split cannot have item_levels")
    if split_type == "file" and any(
        key in rule for key in ("section_level", "category_levels")
    ):
        _fail("section_level and category_levels require headings split")
    if "section_level" in rule:
        if target != "worldbook":
            _fail("section_level is only valid for worldbook")
        section_level = _int(rule["section_level"], "section_level")
        if section_level < 1 or section_level >= min(levels):
            _fail("section_level must be below all item levels")
    if "category_levels" in rule:
        if target not in {"notes", "outlines"} or not isinstance(
            rule["category_levels"], list
        ):
            _fail("category_levels is only valid as a list for notes or outlines")
        category_levels = [
            _int(level, "category_levels") for level in rule["category_levels"]
        ]
        if (
            category_levels != sorted(set(category_levels))
            or any(level < 2 or level > 6 for level in category_levels)
            or any(level >= max(levels) for level in category_levels)
            or len(category_levels) > 2
        ):
            _fail("category_levels must be ascending, at most two, and ancestors")
    if "category_path" in rule and (
        target not in {"notes", "outlines"}
        or not isinstance(rule["category_path"], list)
        or any(
            not isinstance(value, str) or not value for value in rule["category_path"]
        )
    ):
        _fail("category_path must be a list of non-empty strings for notes or outlines")
    if "writing_visible" in rule and (
        target not in {"worldbook", "characters", "notes", "outlines"}
        or not isinstance(rule["writing_visible"], bool)
    ):
        _fail("writing_visible is only a boolean for content targets")
    if "disabled_title_suffix" in rule and (
        target not in {"worldbook", "characters", "notes", "outlines"}
        or not isinstance(rule["disabled_title_suffix"], str)
        or not rule["disabled_title_suffix"]
        or "\n" in rule["disabled_title_suffix"]
        or "\r" in rule["disabled_title_suffix"]
    ):
        _fail("disabled_title_suffix must be a non-empty content-target string")
    if "context_mode" in rule and (
        target != "discussions" or rule["context_mode"] not in {"global", "local"}
    ):
        _fail("context_mode is only valid for discussions")
    return rule


def _mapped_items(path: str, text: str, rule: dict[str, Any]) -> list[MappedSourceItem]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    headings = _scan(text)
    target = rule["target"]
    visible = rule.get("writing_visible", True)
    context = rule.get("context_mode", "global") if target == "discussions" else None
    h1 = next(heading for heading in headings if heading.level == 1)

    def item_title_and_visibility(title: str) -> tuple[str, bool]:
        suffix = rule.get("disabled_title_suffix")
        if not isinstance(suffix, str) or not title.endswith(suffix):
            return title, visible
        clean_title = title[: -len(suffix)].rstrip()
        if not clean_title:
            _fail("disabled title suffix must not consume the whole title")
        return clean_title, False

    if rule["split"]["type"] == "file":
        title, item_visible = item_title_and_visibility(h1.title)
        return [
            MappedSourceItem(
                path,
                rule["id"],
                target,
                "H1:" + title,
                title,
                "\n".join(lines[h1.line + 1 :]).strip("\n"),
                None,
                list(rule.get("category_path", [])),
                item_visible,
                context,
                0,
            )
        ]
    item_levels = set(rule["split"]["item_levels"])
    selected = [heading for heading in headings if heading.level in item_levels]
    if not selected:
        _fail("headings split produced no items")
    results: list[MappedSourceItem] = []
    section_level = rule.get("section_level")
    category_levels = set(rule.get("category_levels", []))
    for heading in selected:
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
        categories = list(rule.get("category_path", []))
        categories.extend(
            item.title for item in ancestors if item.level in category_levels
        )
        if len(categories) > 2:
            _fail("category path cannot exceed two levels")
        anchor = "/".join(
            [
                *(f"H{item.level}:{item.title}" for item in ancestors),
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
                context,
                0,
            )
        )
    return results


def parse_source_mapping(data: bytes, target_project_id: str) -> list[MappedSourceItem]:
    files = read_zip(data)
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
    }:
        _fail("invalid import map fields")
    if (
        config.get("schema") != "openfic.import-map"
        or config.get("version") != 1
        or config.get("project_id") != target_project_id
    ):
        _fail("invalid import map identity")
    rules = config.get("rules")
    if not isinstance(rules, list) or not rules:
        _fail("rules must be non-empty")
    seen_rules: set[str] = set()
    seen_logic: set[tuple[str, str, str]] = set()
    output: list[MappedSourceItem] = []
    orders: dict[str, int] = {}
    for raw_rule in rules:
        rule = _validate_rule(raw_rule)
        if rule["id"] in seen_rules:
            _fail("duplicate rule id")
        seen_rules.add(rule["id"])
        matches = (
            [rule["source"]]
            if isinstance(rule.get("source"), str) and rule["source"]
            else sorted(
                path for path in files if fnmatch.fnmatchcase(path, rule["glob"])
            )
        )
        if not matches:
            _fail("source rule has no matching files")
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
                logic = (item.target, item.source, item.anchor)
                if logic in seen_logic:
                    _fail("duplicate logical object")
                seen_logic.add(logic)
                order = orders.get(item.target, 0)
                output.append(replace(item, order=order))
                orders[item.target] = order + 1
    return output
