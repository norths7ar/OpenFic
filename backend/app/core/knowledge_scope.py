"""Session knowledge scope and its monotonic transition policy."""

from enum import StrEnum


class KnowledgeScope(StrEnum):
    LOCAL = "local"
    GLOBAL = "global"


def merge_known_scope(current: KnowledgeScope, restored: KnowledgeScope) -> KnowledgeScope:
    """A persisted session and its checkpoint can only widen each other's scope."""
    if KnowledgeScope.GLOBAL in (current, restored):
        return KnowledgeScope.GLOBAL
    return KnowledgeScope.LOCAL


def validate_scope_change(
    current: KnowledgeScope,
    requested: KnowledgeScope,
    *,
    supports_global: bool,
) -> None:
    """Validate scope and role changes independently of runtime activity/locking."""
    if current == KnowledgeScope.GLOBAL and requested == KnowledgeScope.LOCAL:
        raise ValueError("已知的全局资料不能遗忘，不能切回公开资料")
    if requested == KnowledgeScope.GLOBAL and not supports_global:
        raise ValueError("全局资料会话不能使用此 Agent，此 Agent 仅支持公开资料")
