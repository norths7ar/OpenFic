from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.agent_visibility import visible_in_scope
from app.core.knowledge_scope import KnowledgeScope
from app.storage.models.character import Character
from app.storage.models.note import Note
from app.storage.models.world_info_entry import WorldInfoEntry


def get_knowledge_scope(state: Mapping[str, Any]) -> KnowledgeScope:
    """Validate runtime scope; missing scope retains the public-material default."""

    return KnowledgeScope(state.get("context_mode", KnowledgeScope.LOCAL))


def character_is_visible(character: Character, *, scope: KnowledgeScope) -> bool:
    return visible_in_scope(character.agent_visibility, scope)


def note_is_visible(note: Note, *, scope: KnowledgeScope) -> bool:
    return visible_in_scope(note.agent_visibility, scope)


def world_entry_is_visible(entry: WorldInfoEntry, *, scope: KnowledgeScope) -> bool:
    return visible_in_scope(entry.agent_visibility, scope)
