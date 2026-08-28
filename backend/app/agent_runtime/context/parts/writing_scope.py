from app.agent_runtime.context.types import ContextMessage


def build_writing_scope(context_mode: str) -> ContextMessage:
    """Describe the immutable knowledge boundary for a scene-draft session."""

    if context_mode == "global":
        scope = (
            "当前场景初稿固定为“作者/编辑范围”。你可以按需读取当前项目的全部正式资料，"
            "包括写作阶段尚不可见的信息；这些资料仅用于起草，不得写回或跨项目混用。"
        )
    else:
        scope = (
            "当前场景初稿固定为“受限创作范围”。你只能读取当前项目中对写作 Agent "
            "可见的资料；被停用或尚未揭示的内容不得读取、推断后混入草稿。"
        )
    return ContextMessage(
        role="system",
        content=scope,
        metadata={"part": "writing_scope", "context_mode": context_mode},
    )
