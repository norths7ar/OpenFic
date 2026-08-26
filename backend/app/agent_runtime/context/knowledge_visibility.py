from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.storage.models.character import Character
from app.storage.models.note import Note
from app.storage.models.world_info_entry import WorldInfoEntry


def includes_all_knowledge(state: Mapping[str, Any]) -> bool:
    """Return whether this immutable discussion context may include spoilers."""

    return state.get("context_mode") == "global"


def character_is_visible(character: Character, *, include_all: bool) -> bool:
    return include_all or character.is_writing_visible


def note_is_visible(note: Note, *, include_all: bool) -> bool:
    return not note.is_hidden and (include_all or note.is_writing_visible)


def world_entry_is_visible(entry: WorldInfoEntry, *, include_all: bool) -> bool:
    return include_all or entry.is_enabled
