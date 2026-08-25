import re
import unicodedata

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
