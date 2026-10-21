import pytest

from app.project_bundle.item_markers import parse_items, render_item


@pytest.mark.parametrize(
    "body",
    [
        "# First\n# Second\n###### Skipped levels",
        "\r\nText\r\n\r\n",
        "\n",
        "",
        "first\rlast\n",
        "```md\n<!-- openfic:item\nid: example\n-->\n```",
        "<!-- openfic:item\n\\<!-- openfic:item\n\\\\<!-- openfic:item",
        "```unfinished\n# Text",
    ],
)
def test_markers_preserve_exact_body_and_cannot_collide(body):
    first = render_item({"id": "one", "title": "Name --> suffix"}, body)
    second = render_item({"id": "two", "title": "Other"}, "second")
    parsed = parse_items(first + second)
    assert [(meta["id"], content) for meta, content in parsed] == [("one", body), ("two", "second")]
    assert parsed[0][0]["title"] == "Name --> suffix"
