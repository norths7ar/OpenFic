from app.agent_runtime.context.types import ContextMessage


def build_discussion_scope(context_mode: str) -> ContextMessage:
    """Describe the immutable knowledge boundary for a Discuss session."""

    if context_mode == "global":
        scope = (
            "当前会话固定为“全局讨论”。你可以按需使用当前项目的全部资料，"
            "包括写作阶段尚不可见的信息；不得跨项目读取或混入其他作品的资料。"
        )
    else:
        scope = (
            "当前会话固定为“局部讨论”。你仍是 Discuss 讨论 Agent；“局部”仅表示"
            "采用与写作 Agent 相同的资料可见边界，并不切换身份或要求直接创作。"
            "你只能使用当前项目中写作阶段可见的资料；"
            "被隐藏或尚不可见的信息视为未知，不得尝试推断、暗示或绕过边界获取。"
        )

    content = (
        "<discussion_scope>\n"
        f"{scope}\n"
        "讨论范围在本会话内不可切换；如需改变范围，应新建讨论会话。\n"
        "</discussion_scope>"
    )
    return ContextMessage(
        role="system",
        content=content,
        metadata={"part": "discussion_scope"},
    )
