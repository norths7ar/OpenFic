"""LLM 调用超时保护与失败重试机制测试。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agent_runtime.graph.llm_invoke import (
    LLMInvokeSettings,
    LLMStreamTimeoutError,
    _TimedStream,
    invoke_model_with_retry,
)


class _FakeResponse:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}


class _StatusError(Exception):
    status_code: int | None = None

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.headers = headers
        if headers is not None:
            self.response = _FakeResponse(headers)


_ZERO_BACKOFF = LLMInvokeSettings(
    retry_base_interval=0.0,
    retry_max_interval=0.0,
)


class _SlowStream:
    def __init__(self, chunks: list[str], delay: float) -> None:
        self._chunks = list(chunks)
        self._delay = delay

    def __aiter__(self) -> _SlowStream:
        return self

    async def __anext__(self) -> str:
        if not self._chunks:
            raise StopAsyncIteration
        await asyncio.sleep(self._delay)
        return self._chunks.pop(0)


class TestTimedStream:


    @pytest.mark.asyncio
    async def test_chunk_idle_timeout(self) -> None:
        stream = _TimedStream(
            _SlowStream(["a"], delay=0.2),
            chunk_timeout=0.05,
        )
        with pytest.raises(LLMStreamTimeoutError, match="chunk idle"):
            await stream.__anext__()


class TestInvokeModelWithRetry:
    @pytest.mark.asyncio
    async def test_retries_transient_failure_and_publishes_event(self) -> None:
        calls: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []

        async def invoke(*args: Any, **kwargs: Any) -> AIMessage:
            calls.append(kwargs)
            if len(calls) == 1:
                raise _StatusError("upstream boom", 503)
            return AIMessage(content="ok")

        async def sink(payload: dict[str, Any]) -> None:
            events.append(payload)

        result = await invoke_model_with_retry(
            object(),
            [HumanMessage(content="hi")],
            invoke=invoke,
            settings=_ZERO_BACKOFF,
            session_id="sess_001",
            node="writer",
            retry_event_sink=sink,
        )

        assert result.content == "ok"
        assert len(calls) == 2
        assert calls[0]["chunk_timeout"] == _ZERO_BACKOFF.chunk_timeout
        assert "total_timeout" not in calls[0]
        assert events == [
            {
                "session_id": "sess_001",
                "node": "writer",
                "attempt": 2,
                "max_attempts": 5,
                "error_type": "_StatusError",
                "error_message": "upstream boom",
                "error_category": "http",
                "retry_in_ms": 0,
            }
        ]
