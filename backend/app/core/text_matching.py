"""Conservative text location helpers that preserve the source text."""

_QUOTE_EQUIVALENTS = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})


def find_unique_quote_equivalent(content: str, query: str) -> int:
    """Return a unique offset, -1 if absent, or -2 if ambiguous.

    Exact matches take precedence. Quote folding is one character to one
    character, so its offsets address the untouched original string.
    """
    if not query:
        raise ValueError("query must not be empty")
    index = content.find(query)
    if index < 0:
        content = content.translate(_QUOTE_EQUIVALENTS)
        query = query.translate(_QUOTE_EQUIVALENTS)
        index = content.find(query)
    if index >= 0 and content.find(query, index + 1) >= 0:
        return -2
    return index
