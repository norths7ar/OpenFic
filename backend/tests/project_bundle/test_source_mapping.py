import pytest
import yaml

from app.project_bundle.archive import BundleFormatError, build_zip
from app.project_bundle.source_mapping import parse_source_mapping


def bundle(project: str, rules: list[dict], **files: str) -> bytes:
    manifest = yaml.safe_dump(
        {
            "schema": "openfic.import-map",
            "version": 1,
            "project_id": project,
            "rules": rules,
        },
        allow_unicode=True,
        sort_keys=True,
    )
    return build_zip({"openfic-import.yaml": manifest, **files})


def test_file_split_and_defaults() -> None:
    data = bundle(
        "p",
        [
            {
                "id": "r",
                "target": "characters",
                "source": "a.md",
                "split": {"type": "file"},
            }
        ],
        **{"a.md": "# 人物\n\n描述"},
    )
    item = parse_source_mapping(data, "p")[0]
    assert (item.title, item.body, item.anchor, item.writing_visible, item.order) == (
        "人物",
        "描述",
        "H1:人物",
        True,
        0,
    )


def test_heading_boundaries_ancestors_and_global_order() -> None:
    rules = [
        {
            "id": "r",
            "target": "notes",
            "glob": "*.md",
            "split": {"type": "headings", "item_levels": [3]},
            "category_levels": [2],
        }
    ]
    data = bundle(
        "p",
        rules,
        **{
            "b.md": (
                "# B\n## Cat B\n### Item B\nB body\n#### detail\nD\n"
                "## Other\n### Item C\nC body"
            ),
            "a.md": "# A\n## Cat A\n### Item A\nA body",
        },
    )
    items = parse_source_mapping(data, "p")
    assert [item.source for item in items] == ["a.md", "b.md", "b.md"]
    assert items[0].title == "Item A"
    assert items[0].category_path == ["Cat A"]
    assert "#### detail" in items[1].body
    assert "## Other" not in items[1].body
    assert "### Item B" not in items[1].body
    assert [item.order for item in items] == list(range(len(items)))


def test_world_section_and_fenced_headings() -> None:
    rules = [
        {
            "id": "r",
            "target": "worldbook",
            "source": "a.md",
            "split": {"type": "headings", "item_levels": [3]},
            "section_level": 2,
        }
    ]
    data = bundle(
        "p",
        rules,
        **{"a.md": "# Root\n## Section\n````md\n# fake\n````\n### Entry ###\nbody"},
    )
    items = parse_source_mapping(data, "p")
    assert [item.title for item in items] == ["Entry"]
    assert items[0].section == "Section"


def test_mixed_outline_levels_use_only_current_ancestor_category() -> None:
    rules = [
        {
            "id": "outline",
            "target": "notes",
            "source": "outline.md",
            "split": {"type": "headings", "item_levels": [2, 3]},
            "category_path": ["提纲"],
            "category_levels": [2],
        }
    ]
    data = bundle(
        "p",
        rules,
        **{
            "outline.md": (
                "# 总纲\n## 第一阶段\n阶段序言\n### 第一卷\n卷内容\n"
                "## 第二阶段\n第二阶段内容"
            )
        },
    )
    items = parse_source_mapping(data, "p")
    assert [(item.title, item.category_path) for item in items] == [
        ("第一阶段", ["提纲"]),
        ("第一卷", ["提纲", "第一阶段"]),
        ("第二阶段", ["提纲"]),
    ]
    assert items[0].body == "阶段序言"
    assert items[1].body == "卷内容"


@pytest.mark.parametrize(
    "mutator",
    [
        lambda r: {**r, "target": "bad"},
        lambda r: {**r, "extra": 1},
        lambda r: {**r, "writing_visible": True},
        lambda r: {**r, "split": {"type": "file", "item_levels": [2]}},
    ],
)
def test_invalid_rule_options(mutator) -> None:
    rule = {
        "id": "r",
        "target": "discussions",
        "source": "a.md",
        "split": {"type": "file"},
    }
    with pytest.raises(BundleFormatError):
        parse_source_mapping(bundle("p", [mutator(rule)], **{"a.md": "# A"}), "p")


def test_rejects_structure_errors_and_isolates_project() -> None:
    rule = {
        "id": "r",
        "target": "notes",
        "source": "a.md",
        "split": {"type": "headings", "item_levels": [2]},
    }
    for text in ("# A\n#### jump", "# A\n## A\n## A"):
        with pytest.raises(BundleFormatError):
            parse_source_mapping(bundle("p", [rule], **{"a.md": text}), "p")
    with pytest.raises(BundleFormatError):
        parse_source_mapping(bundle("other", [rule], **{"a.md": "# A\n## B"}), "p")
    with pytest.raises(BundleFormatError):
        parse_source_mapping(
            bundle("p", [{**rule, "glob": "*.md", "source": None}], **{"a.md": "# A"}),
            "p",
        )
    with pytest.raises(BundleFormatError, match="no matching files"):
        parse_source_mapping(
            bundle(
                "p",
                [{**rule, "source": None, "glob": "missing/*.md"}],
                **{"a.md": "# A\n## B"},
            ),
            "p",
        )
    files = {
        "openfic-import.yaml": yaml.safe_dump(
            {
                "schema": "openfic.import-map",
                "version": 1,
                "project_id": "p",
                "rules": [rule],
                "unknown": True,
            }
        ),
        "a.md": "# A\n## B",
    }
    with pytest.raises(BundleFormatError, match="invalid import map fields"):
        parse_source_mapping(build_zip(files), "p")


def test_categories_max_two_and_duplicate_logic() -> None:
    rule = {
        "id": "r",
        "target": "notes",
        "source": "a.md",
        "split": {"type": "headings", "item_levels": [4]},
        "category_levels": [2, 3],
        "category_path": ["static"],
    }
    with pytest.raises(BundleFormatError):
        parse_source_mapping(
            bundle("p", [rule], **{"a.md": "# A\n## B\n### C\n#### D"}), "p"
        )
