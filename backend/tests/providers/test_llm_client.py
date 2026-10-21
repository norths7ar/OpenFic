from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from app.models.clients.llm_client import _patch_deepseek_reasoning_payload


def test_patch_deepseek_reasoning_payload_adds_reasoning_content() -> None:
    messages = [
        HumanMessage(content="use tool"),
        AIMessage(
            content="",
            additional_kwargs={"reasoning_content": "need chapter content"},
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "read_chapter",
                    "args": {"chapter_ref": {"type": "order", "value": 1}},
                }
            ],
        ),
    ]
    payload: dict[str, Any] = {
        "messages": [
            {"role": "user", "content": "use tool"},
            {"role": "assistant", "content": None, "tool_calls": []},
        ]
    }

    _patch_deepseek_reasoning_payload(messages, payload)

    assert payload["messages"][1]["reasoning_content"] == "need chapter content"
