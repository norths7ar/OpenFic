import io
import zipfile

import pytest

from app.project_bundle.archive import (
    BundleFormatError,
    build_zip,
    read_zip,
)
from app.project_bundle.markdown import (
    parse_markdown_document,
    render_markdown_document,
)
from app.project_bundle.names import slugify_filename


def test_markdown_round_trip_preserves_original_newlines() -> None:
    text = render_markdown_document(
        {"kind": "note", "tags": ["中文"]}, "标题", "\r\n## 小节\r\n正文"
    )
    parsed = parse_markdown_document(text)
    assert parsed.frontmatter["kind"] == "note"
    assert parsed.frontmatter["tags"] == ["中文"]
    assert parsed.title == "标题"
    assert parsed.body == "\r\n## 小节\r\n正文"


def test_markdown_keeps_all_body_headings() -> None:
    parsed = parse_markdown_document("---\na: 1\n---\n# 标题\n```md\n# 代码\n```\n## 小节")
    assert parsed.title == "标题"
    assert parse_markdown_document("---\na: 1\n---\n# 一\n# 二").body == "# 二"
    with pytest.raises(BundleFormatError):
        parse_markdown_document("---\na: 1\n---\n正文\n# 标题")


def test_render_rejects_multiline_title_but_accepts_body_h1() -> None:
    with pytest.raises(BundleFormatError):
        render_markdown_document({}, "一\n二", "")
    assert (
        parse_markdown_document(render_markdown_document({}, "标题", "# 另一个标题")).body
        == "# 另一个标题"
    )


@pytest.mark.parametrize(
    "text", ["# 无 front matter", "---\n[]\n---\n# 标题", "---\na: 1\n---\n## 只有二级"]
)
def test_markdown_rejects_invalid_structure(text: str) -> None:
    with pytest.raises(BundleFormatError):
        parse_markdown_document(text)


def test_zip_is_deterministic_and_round_trips() -> None:
    first = build_zip({"b.md": "二", "a.md": b"one"})
    second = build_zip({"a.md": b"one", "b.md": "二"})
    assert first == second
    assert read_zip(first) == {"a.md": b"one", "b.md": "二".encode()}


def test_zip_skips_safe_directory_entries() -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("notes/", b"")
        archive.writestr("notes/a.md", b"a")
    assert read_zip(stream.getvalue()) == {"notes/a.md": b"a"}


def test_zip_checks_declared_size_before_reading(monkeypatch: pytest.MonkeyPatch) -> None:
    data = build_zip({"a.md": "12"})
    monkeypatch.setattr("app.project_bundle.archive.MAX_FILE_UNCOMPRESSED", 1)
    with pytest.raises(BundleFormatError):
        read_zip(data)


@pytest.mark.parametrize("path", ["/x", "C:/x", "../x", "a/../x", "a\\x", "a//x", ""])
def test_zip_rejects_unsafe_paths(path: str) -> None:
    with pytest.raises(BundleFormatError):
        build_zip({path: "x"})


def test_zip_rejects_duplicate_entries_and_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = io.BytesIO()
    with (
        pytest.warns(UserWarning, match="Duplicate name"),
        zipfile.ZipFile(stream, "w") as archive,
    ):
        archive.writestr("same.md", "one")
        archive.writestr("same.md", "two")
    with pytest.raises(BundleFormatError):
        read_zip(stream.getvalue())
    monkeypatch.setattr("app.project_bundle.archive.MAX_FILE_UNCOMPRESSED", 1)
    with pytest.raises(BundleFormatError):
        build_zip({"big.md": "12"})


def test_zip_rejects_non_zip_and_supports_file_count_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(BundleFormatError):
        read_zip(b"not zip")
    monkeypatch.setattr("app.project_bundle.archive.MAX_FILES", 0)
    with pytest.raises(BundleFormatError):
        build_zip({"a": ""})


@pytest.mark.parametrize(
    "title,expected",
    [("CON.txt", "_CON.txt"), ("  中文 标题  ", "中文-标题"), ("a<>b", "a--b")],
)
def test_slugify_filename_is_windows_safe(title: str, expected: str) -> None:
    assert slugify_filename(title, "fallback") == expected


def test_slugify_filename_uses_fallback_when_title_is_empty() -> None:
    assert slugify_filename("... ", "我的文件") == "我的文件"


def test_slugify_filename_is_bounded_and_trims_after_truncation() -> None:
    result = slugify_filename("a" * 200 + "   ", "fallback")
    assert len(result) == 120
    assert not result.endswith((".", " "))
