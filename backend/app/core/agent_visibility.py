"""Canonical material visibility policy and presentation/export catalog."""

from dataclasses import dataclass
from enum import StrEnum

from app.core.knowledge_scope import KnowledgeScope


class AgentVisibility(StrEnum):
    ALL = "all"
    GLOBAL = "global"
    NONE = "none"


@dataclass(frozen=True)
class AgentVisibilityState:
    value: AgentVisibility
    label: str
    description: str
    export_marker: str
    scopes: tuple[KnowledgeScope, ...]


AGENT_VISIBILITY_STATES = (
    AgentVisibilityState(
        AgentVisibility.ALL,
        "公开",
        "公开资料与全局资料范围的 Agent 均可读取",
        "",
        (KnowledgeScope.LOCAL, KnowledgeScope.GLOBAL),
    ),
    AgentVisibilityState(
        AgentVisibility.GLOBAL,
        "仅全局",
        "仅全局资料范围的 Agent 可读取",
        "[仅全局]",
        (KnowledgeScope.GLOBAL,),
    ),
    AgentVisibilityState(
        AgentVisibility.NONE, "隐藏", "所有 Agent 均不可读取，不影响手动查看和编辑", "[隐藏]", ()
    ),
)
DEFAULT_AGENT_VISIBILITY = AgentVisibility.ALL


def validate_agent_visibility(value: str) -> AgentVisibility:
    return AgentVisibility(value)


def visible_in_scope(value: str, scope: KnowledgeScope) -> bool:
    """Unknown values fail closed, including when loading historical state."""
    return any(state.value == value and scope in state.scopes for state in AGENT_VISIBILITY_STATES)


def values_for_scope(scope: KnowledgeScope) -> tuple[AgentVisibility, ...]:
    return tuple(state.value for state in AGENT_VISIBILITY_STATES if scope in state.scopes)
