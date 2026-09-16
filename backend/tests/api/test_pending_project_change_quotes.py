"""Quote matching proposal regressions."""

import pytest

from app.core.text_matching import find_unique_quote_equivalent
from tests.api.test_pending_project_changes import (
    _create_payload,
    _create_project,
    _post_change,
    _update_payload,
)


@pytest.mark.parametrize(
    "content,query,expected",
    [
        ("前“烬”后", '"烬"', 1),
        ("前‘烬’后", "'烬'", 1),
        ('“烬”与"烬"', '"烬"', 4),  # Exact match takes precedence.
        ("“烬”和“烬”", '"烬"', -2),
        ("“烬”和”烬“", '"烬"', -2),
        ("aaa", "aa", -2),
        ("烬翼", "烬羽", -1),
        ("「烬」", '"烬"', -1),
    ],
)
def test_quote_location(content, query, expected):
    assert find_unique_quote_equivalent(content, query) == expected


async def test_quote_fallback_preserves_surrounding_punctuation(client):
    project = await _create_project(client, "引号容错")
    created = await _post_change(
        client,
        project,
        _create_payload(
            "character",
            after={
                "title": "烬翼",
                "body": "“保留”——‘不动’：“烬”来自黑翼。\n末尾“保留”。",
            },
        ),
    )
    applied = (
        await client.post(f"/api/v1/projects/{project}/pending-changes/{created['id']}/apply")
    ).json()
    proposal = await _post_change(
        client,
        project,
        _update_payload(
            "character",
            applied["target_id"],
            {"edits": [{"old_content": '"烬"来自黑翼。', "new_content": "“烬”源于黑翼。"}]},
        ),
    )
    assert proposal["after"]["body"] == "“保留”——‘不动’：“烬”源于黑翼。\n末尾“保留”。"
