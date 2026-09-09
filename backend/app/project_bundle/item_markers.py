"""Source item envelopes: Markdown headings never describe document structure."""

from __future__ import annotations

import json
import re
from typing import Any

import yaml

from .archive import BundleFormatError
from .markdown import body_format, restore_body_format

_START = "<!-- openfic:item"
_ESCAPED_START = re.compile(r"^(\\*)<!-- openfic:item$", re.MULTILINE)
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_KEYS = {
    "id",
    "title",
    "order",
    "agent_visibility",
    "section",
    "is_locked",
    "is_favorited",
    "body_format",
}


def render_item(metadata: dict[str, Any], body: str) -> str:
    """Escape reserved lines even in code fences, including existing escapes."""
    normalized = body.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    escaped = _ESCAPED_START.sub(lambda match: "\\" + match.group(0), normalized)
    header = yaml.safe_dump(
        {**metadata, "body_format": body_format(body)}, allow_unicode=True, sort_keys=False
    ).rstrip("\n")
    # YAML quoted values may contain comment terminators; keep the HTML valid.
    if "-->" in header:
        header = json.dumps(
            {**metadata, "body_format": body_format(body)}, ensure_ascii=False, indent=2
        ).replace("-->", "--\\u003e")
    return f"{_START}\n{header}\n-->\n{escaped}\n"


def parse_items(text: str) -> list[tuple[dict[str, Any], str]]:
    """Reserved unescaped marker lines are structural, also inside code fences.

    This deliberately does not depend on Markdown parser state: an unfinished
    code fence in one item must never consume the next item. Export escapes all
    literal marker lines; hand-authored examples use the same backslash escape.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    starts = [index for index, line in enumerate(lines) if line == _START]
    if not starts or any(line.strip() for line in lines[: starts[0]]):
        raise BundleFormatError("source file must begin with an openfic:item marker")
    result = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        try:
            close = lines.index("-->", start + 1, end)
        except ValueError as exc:
            raise BundleFormatError("openfic:item metadata is not terminated") from exc
        try:
            metadata = yaml.safe_load("\n".join(lines[start + 1 : close]))
        except yaml.YAMLError as exc:
            raise BundleFormatError("openfic:item metadata is invalid YAML") from exc
        if not isinstance(metadata, dict) or set(metadata) - _KEYS:
            raise BundleFormatError("openfic:item metadata fields are invalid")
        if not isinstance(metadata.get("id"), str) or not _ID.fullmatch(metadata["id"]):
            raise BundleFormatError("openfic:item id is invalid")
        title = metadata.get("title")
        if not isinstance(title, str) or not title.strip() or "\n" in title or "\r" in title:
            raise BundleFormatError("openfic:item title must be a non-empty single line")
        order = metadata.get("order", 0)
        if isinstance(order, bool) or not isinstance(order, int) or order < 0:
            raise BundleFormatError("openfic:item order is invalid")
        for flag in ("is_locked", "is_favorited"):
            if flag in metadata and not isinstance(metadata[flag], bool):
                raise BundleFormatError("openfic:item flag is invalid")
        if "section" in metadata and not isinstance(metadata["section"], str):
            raise BundleFormatError("openfic:item section is invalid")
        body = "\n".join(lines[close + 1 : end]).strip("\n")
        body = _ESCAPED_START.sub(
            lambda match: match.group(0)[1:] if match.group(1) else match.group(0), body
        )
        if "body_format" in metadata:
            body = restore_body_format(body, metadata["body_format"])
        result.append((metadata, body))
    return result
