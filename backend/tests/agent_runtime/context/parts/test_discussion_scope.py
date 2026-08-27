from app.agent_runtime.context.parts.discussion_scope import build_discussion_scope


def test_global_discussion_scope_allows_current_project_hidden_knowledge() -> None:
    message = build_discussion_scope("global")

    assert message.role == "system"
    assert "全局讨论" in message.content
    assert "尚不可见的信息" in message.content
    assert "不得跨项目" in message.content
    assert message.metadata == {"part": "discussion_scope"}


def test_local_discussion_scope_treats_hidden_knowledge_as_unknown() -> None:
    message = build_discussion_scope("local")

    assert message.role == "system"
    assert "局部讨论" in message.content
    assert "仍是 Discuss 讨论 Agent" in message.content
    assert "并不切换身份" in message.content
    assert "视为未知" in message.content
    assert "不得尝试推断" in message.content
    assert "不可切换" in message.content
