"""Knowledge permissions are a shared policy, independent of material type."""

from types import SimpleNamespace

import pytest
from pydantic import TypeAdapter, ValidationError

from app.agent_runtime.context.knowledge_visibility import (
    character_is_visible,
    note_is_visible,
    world_entry_is_visible,
)
from app.core.agent_visibility import AgentVisibility, visible_in_scope
from app.core.knowledge_scope import KnowledgeScope


@pytest.mark.parametrize("check", [character_is_visible, note_is_visible, world_entry_is_visible])
@pytest.mark.parametrize(
    "value,local,global_", [("all", True, True), ("global", False, True), ("none", False, False)]
)
def test_material_knowledge_matrix(check, value, local, global_):
    material = SimpleNamespace(agent_visibility=value)
    assert check(material, scope=KnowledgeScope.LOCAL) is local
    assert check(material, scope=KnowledgeScope.GLOBAL) is global_


@pytest.mark.parametrize("value", ["", "discussion", "unknown", "ALL"])
def test_unknown_visibility_rejected_and_never_readable(value):
    with pytest.raises(ValidationError):
        TypeAdapter(AgentVisibility).validate_python(value)
    assert not visible_in_scope(value, "local")
    assert not visible_in_scope(value, "global")
