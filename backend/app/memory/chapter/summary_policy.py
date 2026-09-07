"""Pure rules for chapter and long-term summaries."""

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.memory.chapter.sequence import global_order_index
from app.storage.models.chapter import Chapter
from app.storage.models.chapter_summary import ChapterSummary
from app.storage.models.project_folder import ProjectFolder
from app.storage.repos.chapter_summary_repo import SUMMARY_STATUS_READY

LONG_TERM_SUMMARY_INTERVAL = 10
MIN_CHAPTER_SUMMARY_WORD_COUNT = 500
SUMMARY_STALE_DIFF_THRESHOLD = 100


@dataclass(frozen=True)
class LongTermSummaryWindow:
    start_order: int
    end_order: int
    chapter_ids: list[str]
    source_summaries: list[ChapterSummary]


def parse_summary_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def encode_summary_list(value: list[str]) -> str:
    return json.dumps(value, ensure_ascii=False)


def is_chapter_summary_skipped(chapter: Chapter) -> bool:
    return chapter.word_count < MIN_CHAPTER_SUMMARY_WORD_COUNT


def is_chapter_summary_stale(summary: ChapterSummary | None, chapter: Chapter) -> bool:
    if summary is None or summary.status != SUMMARY_STATUS_READY:
        return False
    return (
        _diff_character_count(
            summary.source_content_normalized,
            normalize_summary_source_content(chapter.content),
        )
        > SUMMARY_STALE_DIFF_THRESHOLD
    )


def normalize_summary_source_content(content: str) -> str:
    return "".join(
        char
        for char in content
        if not char.isspace() and not unicodedata.category(char).startswith("P")
    )


def _diff_character_count(left: str, right: str) -> int:
    matcher = SequenceMatcher(a=left, b=right, autojunk=False)
    count = 0
    for tag, left_start, left_end, right_start, right_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        count += (left_end - left_start) + (right_end - right_start)
    return count


def chapter_summary_signature(summary: ChapterSummary) -> str:
    payload = json.dumps(
        {
            "chapter_id": summary.chapter_id,
            "source": summary.source_content_normalized,
            "summary": summary.summary,
            "start_time": summary.start_time,
            "end_time": summary.end_time,
            "characters": summary.characters_json,
            "locations": summary.locations_json,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _source_chapter_ids(source_summaries: list[ChapterSummary]) -> list[str]:
    return [summary.chapter_id for summary in source_summaries if summary.chapter_id]


def _window_source_chapter_ids(source_summaries: list[ChapterSummary]) -> list[str]:
    return [
        summary.chapter_id
        for summary in sorted(source_summaries, key=lambda item: item.chapter_order or 0)
        if summary.chapter_id
    ]


def _source_chapter_summary_signatures(source_summaries: list[ChapterSummary]) -> list[str]:
    return [
        chapter_summary_signature(summary)
        for summary in sorted(source_summaries, key=lambda item: item.chapter_order or 0)
    ]


def is_long_term_summary_stale(
    summary: ChapterSummary | None,
    chapters: list[Chapter],
    chapter_summaries: list[ChapterSummary],
    volumes: list[ProjectFolder],
) -> bool:
    if summary is None or summary.status != SUMMARY_STATUS_READY:
        return False
    if summary.start_order is None or summary.end_order is None:
        return True
    window = build_long_term_summary_window(
        chapters,
        volumes,
        chapter_summaries,
        summary.start_order,
        summary.end_order,
    )
    if window is None:
        return True
    saved_chapter_ids = parse_summary_list(summary.source_chapter_ids_json)
    saved_signatures = parse_summary_list(summary.source_chapter_summary_signatures_json)
    current_signatures = _source_chapter_summary_signatures(window.source_summaries)
    return saved_chapter_ids != window.chapter_ids or saved_signatures != current_signatures


def _fixed_summary_windows(
    chapters: list[Chapter],
    volumes: list[ProjectFolder],
    size: int,
) -> list[list[Chapter]]:
    order_map = global_order_index(chapters, volumes)
    ordered = sorted(chapters, key=lambda chapter: order_map.get(chapter.id, float("inf")))
    windows: list[list[Chapter]] = []
    for start in range(1, len(ordered) + 1, size):
        group = [chapter for chapter in ordered if start <= order_map[chapter.id] < start + size]
        if len(group) == size:
            windows.append(group)
    return windows


def _build_long_term_window_from_group(
    chapter_group: list[Chapter],
    order_map: dict[str, int],
    summary_by_chapter_id: dict[str | None, ChapterSummary],
) -> LongTermSummaryWindow | None:
    source_summaries: list[ChapterSummary] = []
    for chapter in sorted(chapter_group, key=lambda item: order_map.get(item.id, float("inf"))):
        if is_chapter_summary_skipped(chapter):
            continue
        summary = summary_by_chapter_id.get(chapter.id)
        if summary is None or summary.status != SUMMARY_STATUS_READY:
            return None
        source_summaries.append(summary)
    if not source_summaries:
        return None
    ordered_chapters = sorted(chapter_group, key=lambda item: order_map.get(item.id, float("inf")))
    return LongTermSummaryWindow(
        start_order=order_map[ordered_chapters[0].id],
        end_order=order_map[ordered_chapters[-1].id],
        chapter_ids=[chapter.id for chapter in ordered_chapters],
        source_summaries=source_summaries,
    )


def build_long_term_summary_window(
    chapters: list[Chapter],
    volumes: list[ProjectFolder],
    chapter_summaries: list[ChapterSummary],
    start_order: int,
    end_order: int,
) -> LongTermSummaryWindow | None:
    summary_by_chapter_id = {summary.chapter_id: summary for summary in chapter_summaries}
    order_map = global_order_index(chapters, volumes)
    chapter_group = [
        chapter for chapter in chapters if start_order <= order_map.get(chapter.id, -1) <= end_order
    ]
    if len(chapter_group) != end_order - start_order + 1:
        return None
    return _build_long_term_window_from_group(chapter_group, order_map, summary_by_chapter_id)


def list_eligible_long_term_ranges(
    chapters: list[Chapter],
    volumes: list[ProjectFolder],
    chapter_summaries: list[ChapterSummary],
) -> list[tuple[int, int]]:
    summary_by_chapter_id = {summary.chapter_id: summary for summary in chapter_summaries}
    order_map = global_order_index(chapters, volumes)
    ranges: list[tuple[int, int]] = []
    for chapter_group in _fixed_summary_windows(chapters, volumes, LONG_TERM_SUMMARY_INTERVAL):
        window = _build_long_term_window_from_group(chapter_group, order_map, summary_by_chapter_id)
        if window is None:
            continue
        ranges.append((window.start_order, window.end_order))
    return ranges


def list_ready_unaggregated_long_term_windows(
    chapters: list[Chapter],
    volumes: list[ProjectFolder],
    chapter_summaries: list[ChapterSummary],
    long_term_summaries: list[ChapterSummary],
) -> list[LongTermSummaryWindow]:
    summary_by_chapter_id = {summary.chapter_id: summary for summary in chapter_summaries}
    order_map = global_order_index(chapters, volumes)
    long_term_by_range = {
        (summary.start_order, summary.end_order): summary
        for summary in long_term_summaries
        if summary.start_order is not None and summary.end_order is not None
    }
    windows: list[LongTermSummaryWindow] = []
    for chapter_group in _fixed_summary_windows(chapters, volumes, LONG_TERM_SUMMARY_INTERVAL):
        window = _build_long_term_window_from_group(chapter_group, order_map, summary_by_chapter_id)
        if window is None:
            continue
        existing = long_term_by_range.get((window.start_order, window.end_order))
        if existing is not None and not is_long_term_summary_stale(
            existing, chapters, chapter_summaries, volumes
        ):
            continue
        windows.append(window)
    return windows
