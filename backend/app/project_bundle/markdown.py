import re
from dataclasses import dataclass
from typing import Any

import yaml

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
    heading_indexes: list[int] = []
    fenced = False
    fence_marker = ""
    for index, line in enumerate(content):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not fenced:
                fenced, fence_marker = True, marker
            elif marker == fence_marker:
                fenced = False
            continue
        if not fenced and _H1.match(line):
            heading_indexes.append(index)
    if len(heading_indexes) != 1:
        raise BundleFormatError("Markdown document must contain exactly one file-level H1")
    heading_index = heading_indexes[0]
    heading_match = _H1.match(content[heading_index])
    if heading_match is None:
        raise BundleFormatError("Markdown document must contain exactly one file-level H1")
    title = heading_match.group(1).strip()
    if "\n" in title or "\r" in title:
        raise BundleFormatError("H1 title must be a single line")
    if not title:
        raise BundleFormatError("H1 title must not be empty")
    body = "\n".join(content[heading_index + 1 :]).strip("\n")
    return ParsedMarkdownDocument(frontmatter=frontmatter, title=title, body=body)


def render_markdown_document(frontmatter: dict[str, Any], title: str, body: str) -> str:
    if not isinstance(frontmatter, dict):
        raise BundleFormatError("front matter must be a mapping")
    if "\n" in title or "\r" in title:
        raise BundleFormatError("H1 title must be a single line")
    if not title.strip():
        raise BundleFormatError("H1 title must not be empty")
    normalized_body = body.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    yaml_text = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=True).rstrip("\n")
    result = f"---\n{yaml_text}\n---\n# {title.strip()}"
    rendered = f"{result}\n{normalized_body}\n" if normalized_body else f"{result}\n"
    parse_markdown_document(rendered)
    return rendered
