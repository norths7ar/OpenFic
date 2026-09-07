"""Direct tests for the pure chapter-summary policy module."""

from app.memory.chapter.summary_policy import (
    MIN_CHAPTER_SUMMARY_WORD_COUNT,
    build_long_term_summary_window,
    encode_summary_list,
    is_chapter_summary_stale,
    normalize_summary_source_content,
    parse_summary_list,
)
from app.storage.models.chapter import Chapter
from app.storage.models.chapter_summary import ChapterSummary
from app.storage.models.project_folder import ProjectFolder as Volume
from app.storage.repos.chapter_summary_repo import SUMMARY_STATUS_READY, SUMMARY_TYPE_CHAPTER


def _chapter(chapter_id: str, volume_id: str, order: int, *, word_count: int = 1000) -> Chapter:
    return Chapter(
        id=chapter_id,
        project_id="project-1",
        volume_id=volume_id,
        title=chapter_id,
        content=f"正文 {chapter_id}",
        order=order,
        word_count=word_count,
    )


def _summary(chapter: Chapter, order: int) -> ChapterSummary:
    return ChapterSummary(
        id=f"summary-{chapter.id}",
        project_id=chapter.project_id,
        summary_type=SUMMARY_TYPE_CHAPTER,
        status=SUMMARY_STATUS_READY,
        chapter_id=chapter.id,
        volume_id=chapter.volume_id,
        chapter_order=order,
        start_order=order,
        end_order=order,
        source_content_normalized=normalize_summary_source_content(chapter.content),
    )


def test_parse_and_encode_summary_list_are_tolerant_of_legacy_values() -> None:
    assert encode_summary_list(["林舟", "旧城"]) == '["林舟", "旧城"]'
    assert parse_summary_list('["林舟", 3, "  "]') == ["林舟", "3"]
    assert parse_summary_list("not-json") == []
    assert parse_summary_list('{"not": "a list"}') == []


def test_chapter_summary_staleness_ignores_whitespace_and_punctuation() -> None:
    chapter = _chapter("c1", "v1", 1)
    chapter.content = "正文， c1！\n"
    summary = _summary(chapter, 1)

    chapter.content = "正文c1"

    assert is_chapter_summary_stale(summary, chapter) is False


def test_long_term_window_keeps_short_chapter_at_global_boundary() -> None:
    volumes = [
        Volume(scope="writing", id="v1", project_id="project-1", title="第一卷", order=1),
        Volume(scope="writing", id="v2", project_id="project-1", title="第二卷", order=2),
    ]
    chapters = [
        *[_chapter(f"c1-{index}", "v1", index) for index in range(1, 6)],
        *[_chapter(f"c2-{index}", "v2", index) for index in range(1, 6)],
    ]
    chapters[0].word_count = MIN_CHAPTER_SUMMARY_WORD_COUNT - 1
    summaries = [_summary(chapter, index) for index, chapter in enumerate(chapters[1:], start=2)]

    window = build_long_term_summary_window(chapters, volumes, summaries, 1, 10)

    assert window is not None
    assert window.chapter_ids == [chapter.id for chapter in chapters]
    assert [summary.chapter_id for summary in window.source_summaries] == [
        chapter.id for chapter in chapters[1:]
    ]
