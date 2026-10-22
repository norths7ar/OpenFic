from typing import Final

type ReasoningEffort = str

DEFAULT_TEMPERATURE: Final = 1.0
DEFAULT_TOP_P: Final = 1.0
DEFAULT_TOP_K: Final = 0
DEFAULT_FREQUENCY_PENALTY: Final = 0.0
DEFAULT_PRESENCE_PENALTY: Final = 0.0
DEFAULT_REPETITION_PENALTY: Final = 1.0
DEFAULT_MIN_P: Final = 0.0
DEFAULT_TOP_A: Final = 0.0
DEFAULT_CONTEXT_LENGTH: Final = 128_000
MAX_CONTEXT_LENGTH: Final = 2_000_000


def is_non_default(value: object, default: object) -> bool:
    return value != default


def with_default[T](value: T | None, default: T) -> T:
    return default if value is None else value
