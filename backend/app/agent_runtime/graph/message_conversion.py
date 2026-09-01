"""Conversions between LangChain messages and OpenFic history records."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.agent_runtime.content_blocks import extract_text_content


def _to_history_dict(m: BaseMessage) -> dict:
    """把 LangChain BaseMessage 反向转成 build_context 期望的 history dict。"""
    # 用 isinstance 判断而非 m.type 字符串：流式累加产生的 *Chunk 子类
    # （如 AIMessageChunk）的 .type 是类名（"AIMessageChunk"）而非 "ai"，
    # 会导致 role 映射失败。
    if isinstance(m, ToolMessage):
        role = "tool"
    elif isinstance(m, AIMessage):
        role = "assistant"
    elif isinstance(m, HumanMessage):
        role = "user"
    elif isinstance(m, SystemMessage):
        role = "system"
    else:
        role = m.type
    response_metadata = getattr(m, "response_metadata", None)
    response_metadata = response_metadata if isinstance(response_metadata, dict) else {}
    metadata: dict[str, Any] = {"part": "history"}
    seq = response_metadata.get("openfic_seq")
    if type(seq) is int:
        metadata["seq"] = seq
    tool_name = response_metadata.get("openfic_tool_name")
    if isinstance(tool_name, str) and tool_name:
        metadata["tool_name"] = tool_name
    out: dict = {
        "role": role,
        "content": extract_text_content(m.content),
        "metadata": metadata,
    }
    if isinstance(m, HumanMessage):
        additional_kwargs = getattr(m, "additional_kwargs", None)
        attachments = (
            additional_kwargs.get("openfic_attachments")
            if isinstance(additional_kwargs, dict)
            else None
        )
        if isinstance(attachments, list):
            out["additional_kwargs"] = {"openfic_attachments": attachments}
    if isinstance(m, AIMessage) and m.tool_calls:
        out["tool_calls"] = list(m.tool_calls)
    if isinstance(m, AIMessage):
        additional_kwargs = getattr(m, "additional_kwargs", None)
        if isinstance(additional_kwargs, dict) and additional_kwargs:
            out["additional_kwargs"] = dict(additional_kwargs)
        else:
            reasoning_content = getattr(m, "reasoning_content", None)
            if isinstance(reasoning_content, str) and reasoning_content:
                out["additional_kwargs"] = {"reasoning_content": reasoning_content}
            else:
                if isinstance(response_metadata, dict):
                    for key in ("reasoning_content", "reasoning"):
                        value = response_metadata.get(key)
                        if isinstance(value, str) and value:
                            out["additional_kwargs"] = {"reasoning_content": value}
                            break
    if isinstance(m, ToolMessage):
        out["tool_call_id"] = m.tool_call_id
        if isinstance(tool_name, str) and tool_name:
            out["name"] = tool_name
        else:
            message_name = getattr(m, "name", None)
            if isinstance(message_name, str) and message_name:
                out["name"] = message_name
    return out
