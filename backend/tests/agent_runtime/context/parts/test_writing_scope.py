from app.agent_runtime.context.parts.writing_scope import build_writing_scope


def test_global_writing_scope_allows_current_project_author_knowledge() -> None:
    message = build_writing_scope("global")

    assert message.role == "system"
    assert "全局资料" in message.content
    assert "所有 Agent 不可见" in message.content
    assert "不得写回或跨项目" in message.content
    assert message.metadata == {"part": "writing_scope", "context_mode": "global"}


def test_local_writing_scope_keeps_hidden_material_out_of_draft() -> None:
    message = build_writing_scope("local")

    assert message.role == "system"
    assert "公开资料" in message.content
    assert "全部 Agent" in message.content
    assert "不得读取" in message.content
    assert message.metadata == {"part": "writing_scope", "context_mode": "local"}
