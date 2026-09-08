from app.agent_runtime.context.types import ContextMessage


def build_discussion_scope(context_mode: str) -> ContextMessage:
    """Describe the session's current, monotonically widening knowledge scope."""

    if context_mode == "global":
        scope = (
            "当前知识范围为“全局资料”。你可以按需使用当前项目中标为“全部 Agent”"
            "或“仅全局 Agent”的资料；标为“所有 Agent 不可见”的资料仍不可读取。"
            "不得跨项目读取或混入其他作品的资料。"
        )
    else:
        scope = (
            "当前知识范围为“公开资料”。你只能使用当前项目中标为“全部 Agent”的资料。"
            "其他资料视为未知，不得尝试推断、暗示或绕过边界获取。"
        )

    content = (
        "<discussion_scope>\n"
        f"{scope}\n"
        "知识范围不改变 Agent 身份。公开资料可在一轮结束后升级为全局资料；"
        "已知信息不能遗忘，全局资料会话不能切回公开资料或 Build。子 Agent 继承知识范围。\n"
        "</discussion_scope>"
    )
    return ContextMessage(
        role="system",
        content=content,
        metadata={"part": "discussion_scope"},
    )
