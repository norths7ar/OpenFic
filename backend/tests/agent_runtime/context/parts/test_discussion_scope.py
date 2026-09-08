from app.agent_runtime.context.parts.discussion_scope import build_discussion_scope


def test_global_discussion_scope_allows_current_project_hidden_knowledge() -> None:
    message = build_discussion_scope("global")

    assert message.role == "system"
    assert "全局资料" in message.content
    assert "所有 Agent 不可见" in message.content
    assert "不得跨项目" in message.content
    assert message.metadata == {"part": "discussion_scope"}


def test_local_discussion_scope_treats_hidden_knowledge_as_unknown() -> None:
    message = build_discussion_scope("local")

    assert message.role == "system"
    assert "公开资料" in message.content
    assert "知识范围不改变 Agent 身份" in message.content
    assert "升级为全局资料" in message.content
    assert "视为未知" in message.content
    assert "不得尝试推断" in message.content
    assert "不能切回公开资料" in message.content
