"""Tests for :mod:`app.agent_runtime.tools.text_match`."""


from app.agent_runtime.tools.text_match import (
    FuzzyReplaceResult,
    fuzzy_replace,
)

# ---------------------------------------------------------------------------
# normalize_for_fuzzy_match
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# fuzzy_replace - exact match path
# ---------------------------------------------------------------------------


def test_exact_match_replaces_first_occurrence_only() -> None:
    result = fuzzy_replace("a a a", "a", "b")
    assert result == FuzzyReplaceResult("b a a", used_fuzzy_match=False)


def test_exact_match_replace_all_replaces_every_occurrence() -> None:
    result = fuzzy_replace("a a a", "a", "b", replace_all=True)
    assert result == FuzzyReplaceResult("b b b", used_fuzzy_match=False)


def test_returns_none_when_no_match() -> None:
    assert fuzzy_replace("hello world", "missing", "x") is None


# ---------------------------------------------------------------------------
# fuzzy_replace - fuzzy match path
# ---------------------------------------------------------------------------


def test_fuzzy_match_preserves_unchanged_lines() -> None:
    # The untouched first line keeps its NBSP and trailing whitespace; only the
    # touched line (which requires fuzzy matching via its NBSP) is rewritten
    # from the normalized base.
    content = "keep\u00a0me   \nchange\u00a0me\n"
    result = fuzzy_replace(content, "change me", "CHANGED")
    assert result == FuzzyReplaceResult("keep\u00a0me   \nCHANGED\n", used_fuzzy_match=True)


# ---------------------------------------------------------------------------
# fuzzy_replace - line ending normalization
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# fuzzy_replace - edge cases
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# fuzzy_replace - whitespace-only old_text collapses to empty (regression)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# fuzzy_replace - escaped whitespace fallback
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# fuzzy_replace - replace_all fuzzy path must be linear (regression)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# fuzzy_replace - stripped trailing whitespace must not match a prefix
# ---------------------------------------------------------------------------
