from app.agent_runtime.context.parts.writing_scope import build_writing_scope


def test_global_writing_scope_allows_current_project_author_knowledge() -> None:
    message = build_writing_scope("global")

    assert message.role == "system"
    assert "作者/编辑范围" in message.content
    assert "当前项目的全部正式资料" in message.content
    assert "不得写回或跨项目" in message.content
    assert message.metadata == {"part": "writing_scope", "context_mode": "global"}


def test_local_writing_scope_keeps_hidden_material_out_of_draft() -> None:
    message = build_writing_scope("local")

    assert message.role == "system"
    assert "受限创作范围" in message.content
    assert "对写作 Agent 可见" in message.content
    assert "不得读取" in message.content
    assert message.metadata == {"part": "writing_scope", "context_mode": "local"}
