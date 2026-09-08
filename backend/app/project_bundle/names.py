import re
import unicodedata
from collections.abc import Iterable

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = (
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
MAX_FILENAME_LENGTH = 120


def slugify_filename(title: str, fallback: str = "untitled") -> str:
    def clean(value: str) -> str:
        value = unicodedata.normalize("NFKC", value).strip()
        value = _INVALID.sub("-", value)
        value = re.sub(r"\s+", "-", value)
        return value[:MAX_FILENAME_LENGTH].rstrip(" .")

    result = clean(title) or clean(fallback) or "untitled"
    stem = result.split(".", 1)[0].upper()
    if stem in _RESERVED:
        result = f"_{result}"
    return result


def chapter_paths(
    chapters: Iterable[tuple[str, str, str | None]],
    volume_titles: dict[str, str],
) -> dict[str, str]:
    """Return readable, collision-safe ``正文`` paths keyed by chapter ID.

    A title is kept as-is when it is a valid Windows filename.  The stable ID
    is only appended where normalisation would make two sibling names collide.
    Volume IDs are handled the same way, so identically titled volumes cannot
    silently share a directory.
    """

    def safe_title(title: str, fallback: str) -> str:
        value = unicodedata.normalize("NFKC", title).strip()
        value = _INVALID.sub("-", value).rstrip(" .")[:MAX_FILENAME_LENGTH].rstrip(" .")
        if not value:
            value = slugify_filename(fallback, "untitled")
        if value.split(".", 1)[0].upper() in _RESERVED:
            value = f"_{value}"
        return value

    chapter_list = list(chapters)
    unknown_volumes = {
        volume_id
        for _chapter_id, _title, volume_id in chapter_list
        if volume_id is not None and volume_id not in volume_titles
    }
    if unknown_volumes:
        raise ValueError("chapter volume is missing")

    volume_stems = {
        volume_id: safe_title(title, volume_id) for volume_id, title in volume_titles.items()
    }
    volume_counts: dict[str, int] = {}
    for stem in volume_stems.values():
        key = stem.casefold()
        volume_counts[key] = volume_counts.get(key, 0) + 1
    directories = {
        volume_id: (
            f"正文/{stem}--{volume_id}" if volume_counts[stem.casefold()] > 1 else f"正文/{stem}"
        )
        for volume_id, stem in volume_stems.items()
    }

    stems = {
        chapter_id: safe_title(title, chapter_id) for chapter_id, title, _volume_id in chapter_list
    }
    sibling_counts: dict[tuple[str, str], int] = {}
    for chapter_id, _title, volume_id in chapter_list:
        directory = "正文" if volume_id is None else directories[volume_id]
        key = (directory, stems[chapter_id].casefold())
        sibling_counts[key] = sibling_counts.get(key, 0) + 1
    paths: dict[str, str] = {}
    for chapter_id, _title, volume_id in chapter_list:
        directory = "正文" if volume_id is None else directories[volume_id]
        stem = stems[chapter_id]
        suffix = f"--{chapter_id}" if sibling_counts[(directory, stem.casefold())] > 1 else ""
        paths[chapter_id] = f"{directory}/{stem}{suffix}.md"
    return paths
