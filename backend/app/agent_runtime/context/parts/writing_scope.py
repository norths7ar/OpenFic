from app.agent_runtime.context.types import ContextMessage


def build_writing_scope(context_mode: str) -> ContextMessage:
    """Describe the knowledge boundary for a scene-draft session."""

    if context_mode == "global":
        scope = (
            "当前场景初稿使用“全局资料”。你只能读取当前项目中标为“全部 Agent”或"
            "“仅全局 Agent”的正式资料；“所有 Agent 不可见”的资料不得读取。"
            "这些资料仅用于起草，不得写回或跨项目混用。"
        )
    else:
        scope = (
            "当前场景初稿使用“公开资料”。你只能读取当前项目中标为“全部 Agent”的资料；"
            "其他资料不得读取、推断后混入草稿。"
        )
    return ContextMessage(
        role="system",
        content=scope,
        metadata={"part": "writing_scope", "context_mode": context_mode},
    )
