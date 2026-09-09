import re
from dataclasses import dataclass
from typing import Any

import yaml

from app.core.agent_visibility import AgentVisibility

from .archive import BundleFormatError


@dataclass(frozen=True)
class ParsedMarkdownDocument:
    frontmatter: dict[str, Any]
    title: str
    body: str


_H1 = re.compile(r"^#\s+(.+?)\s*$")
_FRONTMATTER = re.compile(r"^---\s*$")


def _lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def body_format(body: str) -> dict[str, Any]:
    """Keep source framing separate from the document's own line endings."""
    core = body.strip("\r\n")
    start = len(body) - len(body.lstrip("\r\n"))
    if not core:
        return {"prefix": body, "suffix": "", "line_ending": "\n"}
    endings = re.findall(r"\r\n|\r|\n", core)
    result: dict[str, Any] = {"prefix": body[:start], "suffix": body[start + len(core) :]}
    if len(set(endings)) <= 1:
        result["line_ending"] = endings[0] if endings else "\n"
    else:
        result["line_endings"] = endings
    return result


def restore_body_format(body: str, format: Any) -> str:
    if not isinstance(format, dict) or set(format) - {
        "prefix",
        "suffix",
        "line_ending",
        "line_endings",
    }:
        raise BundleFormatError("body_format is invalid")
    for key in ("prefix", "suffix"):
        value = format.get(key)
        if not isinstance(value, str) or value.strip("\r\n"):
            raise BundleFormatError("body_format boundary must contain only line endings")
    if "line_ending" in format:
        if (
            "line_endings" in format
            or not isinstance(format["line_ending"], str)
            or format["line_ending"] not in {"\n", "\r\n", "\r"}
        ):
            raise BundleFormatError("body_format line ending is invalid")
        core = body.replace("\n", format["line_ending"])
    else:
        endings = format.get("line_endings")
        if (
            not isinstance(endings, list)
            or not endings
            or any(
                not isinstance(value, str) or value not in {"\n", "\r\n", "\r"} for value in endings
            )
        ):
            raise BundleFormatError("body_format line endings are invalid")
        lines = body.split("\n")
        core = lines[0] + "".join(
            (endings[index] if index < len(endings) else "\n") + line
            for index, line in enumerate(lines[1:])
        )
    return format["prefix"] + core + format["suffix"]


def parse_markdown_document(text: str) -> ParsedMarkdownDocument:
    lines = _lines(text)
    if not lines or not _FRONTMATTER.match(lines[0]):
        raise BundleFormatError("Markdown document must start with YAML front matter")
    try:
        closing = next(i for i in range(1, len(lines)) if _FRONTMATTER.match(lines[i]))
    except StopIteration as exc:
        raise BundleFormatError("YAML front matter is not closed") from exc
    try:
        frontmatter = yaml.safe_load("\n".join(lines[1:closing]))
    except yaml.YAMLError as exc:
        raise BundleFormatError("front matter is not valid YAML") from exc
    if not isinstance(frontmatter, dict):
        raise BundleFormatError("front matter must be a mapping")

    content = lines[closing + 1 :]
    first_content = next((line for line in content if line.strip()), None)
    if first_content is None or _H1.match(first_content) is None:
        raise BundleFormatError("the first non-empty content line must be the H1")
    # Only the leading title is an envelope. All later headings belong to the body.
    heading_index = next(index for index, line in enumerate(content) if line.strip())
    heading_match = _H1.match(content[heading_index])
    if heading_match is None:
        raise BundleFormatError("Markdown document must contain exactly one file-level H1")
    title = heading_match.group(1).strip()
    if "\n" in title or "\r" in title:
        raise BundleFormatError("H1 title must be a single line")
    if not title:
        raise BundleFormatError("H1 title must not be empty")
    body = "\n".join(content[heading_index + 1 :]).strip("\n")
    if "body_format" in frontmatter:
        body = restore_body_format(body, frontmatter["body_format"])
    return ParsedMarkdownDocument(frontmatter=frontmatter, title=title, body=body)


def render_markdown_document(frontmatter: dict[str, Any], title: str, body: str) -> str:
    if not isinstance(frontmatter, dict):
        raise BundleFormatError("front matter must be a mapping")
    if "\n" in title or "\r" in title:
        raise BundleFormatError("H1 title must be a single line")
    if not title.strip():
        raise BundleFormatError("H1 title must not be empty")
    normalized_body = body.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    rendered_frontmatter = {
        key: value.value if isinstance(value, AgentVisibility) else value
        for key, value in frontmatter.items()
        if key != "body_format"
    }
    if normalized_body != body:
        rendered_frontmatter["body_format"] = body_format(body)
    yaml_text = yaml.safe_dump(rendered_frontmatter, allow_unicode=True, sort_keys=True).rstrip(
        "\n"
    )
    result = f"---\n{yaml_text}\n---\n# {title.strip()}"
    rendered = f"{result}\n{normalized_body}\n" if normalized_body else f"{result}\n"
    parse_markdown_document(rendered)
    return rendered
