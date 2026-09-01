from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from app.agent_runtime.graph.message_conversion import _to_history_dict


def test_to_history_dict_preserves_reasoning_content() -> None:
    message = AIMessage(
        content="",
        additional_kwargs={"reasoning_content": "先分析"},
        tool_calls=[{"id": "call_1", "name": "noop", "args": {}}],
    )

    out = _to_history_dict(message)

    assert out["additional_kwargs"] == {"reasoning_content": "先分析"}
    assert out["tool_calls"][0]["id"] == "call_1"
    assert out["tool_calls"][0]["name"] == "noop"
    assert out["tool_calls"][0]["args"] == {}


def test_to_history_dict_uses_response_metadata_reasoning_content() -> None:
    message = AIMessage(
        content="",
        response_metadata={"reasoning_content": "从 metadata 来的思考"},
    )

    out = _to_history_dict(message)

    assert out["additional_kwargs"] == {"reasoning_content": "从 metadata 来的思考"}


def test_to_history_dict_uses_openfic_response_metadata_for_internal_history_fields() -> None:
    human = HumanMessage(
        content="hi",
        response_metadata={"openfic_seq": 7},
    )
    tool = ToolMessage(
        content="result",
        tool_call_id="call_1",
        response_metadata={
            "openfic_seq": 8,
            "openfic_tool_name": "read_chapter",
        },
    )

    human_out = _to_history_dict(human)
    tool_out = _to_history_dict(tool)

    assert human_out["metadata"] == {"part": "history", "seq": 7}
    assert tool_out["metadata"] == {
        "part": "history",
        "seq": 8,
        "tool_name": "read_chapter",
    }
    assert tool_out["name"] == "read_chapter"


def test_to_history_dict_preserves_only_openfic_attachment_metadata() -> None:
    message = HumanMessage(
        content="图片请求",
        additional_kwargs={
            "openfic_attachments": [{"id": "image-1"}],
            "unrelated": "must-not-persist",
        },
    )

    assert _to_history_dict(message)["additional_kwargs"] == {
        "openfic_attachments": [{"id": "image-1"}]
    }


def test_to_history_dict_normalizes_ai_message_chunk_role() -> None:
    # _invoke_model 累加流式分片后返回 AIMessageChunk（AIMessage 子类），
    # 其 .type 为 "AIMessageChunk" 而非 "ai"，必须仍映射为 assistant。
    chunk = AIMessageChunk(
        content="hello",
        tool_calls=[{"id": "c1", "name": "noop", "args": {}}],
        additional_kwargs={"reasoning_content": "思考"},
    )

    out = _to_history_dict(chunk)

    assert out["role"] == "assistant"
    assert out["content"] == "hello"
    assert out["tool_calls"][0]["id"] == "c1"
    assert out["additional_kwargs"] == {"reasoning_content": "思考"}
