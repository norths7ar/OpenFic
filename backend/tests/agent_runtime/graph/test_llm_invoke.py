"""LLM 调用超时保护与失败重试机制测试。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agent_runtime.context.compaction.service import CompactionError
from app.agent_runtime.graph.llm_invoke import (
    LLMInvokeSettings,
    LLMStreamTimeoutError,
    RetryCategory,
    RetryDecision,
    _TimedStream,
    classify_error,
    compute_retry_delay,
    extract_retry_after_ms,
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


class TestClassifyError:


    def test_no_retry_quota_on_429(self) -> None:
        outcome = classify_error(_StatusError("insufficient_quota", 429))
        assert outcome.decision is RetryDecision.NO_RETRY
        assert outcome.category is RetryCategory.QUOTA


    def test_no_retry_auth_status(self) -> None:
        outcome = classify_error(_StatusError("invalid api key", 401))
        assert outcome.decision is RetryDecision.NO_RETRY
        assert outcome.category is RetryCategory.AUTH

    def test_no_retry_auth_text(self) -> None:
        outcome = classify_error(RuntimeError("authentication failed"))
        assert outcome.decision is RetryDecision.NO_RETRY
        assert outcome.category is RetryCategory.AUTH

    def test_no_retry_quota_text(self) -> None:
        outcome = classify_error(RuntimeError("you have exceeded your quota"))
        assert outcome.decision is RetryDecision.NO_RETRY
        assert outcome.category is RetryCategory.QUOTA

    def test_no_retry_context_overflow(self) -> None:
        outcome = classify_error(RuntimeError("maximum context length exceeded"))
        assert outcome.decision is RetryDecision.NO_RETRY
        assert outcome.category is RetryCategory.CONTEXT_OVERFLOW







    def test_no_retry_compaction_error(self) -> None:
        outcome = classify_error(CompactionError("llm_error", "压缩失败"))
        assert outcome.decision is RetryDecision.NO_RETRY
        assert outcome.category is RetryCategory.CONTEXT_OVERFLOW

    def test_no_retry_unclassified(self) -> None:
        outcome = classify_error(RuntimeError("boom"))
        assert outcome.decision is RetryDecision.NO_RETRY
        assert outcome.category is RetryCategory.OTHER

    def test_no_retry_cancelled(self) -> None:
        outcome = classify_error(asyncio.CancelledError())
        assert outcome.decision is RetryDecision.NO_RETRY


class TestExtractRetryAfterMs:
    def test_prefers_retry_after_ms_header(self) -> None:
        exc = _StatusError("rate limited", 429, headers={"retry-after-ms": "1500"})
        assert extract_retry_after_ms(exc) == 1500.0

    def test_retry_after_seconds(self) -> None:
        exc = _StatusError("rate limited", 429, headers={"retry-after": "5"})
        assert extract_retry_after_ms(exc) == 5000.0

    def test_retry_after_http_date(self) -> None:
        future = datetime.now(UTC) + timedelta(seconds=60)
        date_header = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
        exc = _StatusError("rate limited", 429, headers={"retry-after": date_header})
        value = extract_retry_after_ms(exc)
        assert value is not None
        assert 50_000 < value < 70_000


class TestComputeRetryDelay:


    def test_retry_after_header_wins(self) -> None:
        exc = _StatusError("rate limited", 429, headers={"retry-after": "3"})
        assert (
            compute_retry_delay(
                exc,
                attempt=1,
                base_interval=2.0,
                max_interval=30.0,
            )
            == 3.0
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

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises_final_error(self) -> None:
        calls = 0
        events: list[dict[str, Any]] = []

        async def invoke(*args: Any, **kwargs: Any) -> AIMessage:
            nonlocal calls
            calls += 1
            raise _StatusError("boom", 503)

        async def sink(payload: dict[str, Any]) -> None:
            events.append(payload)

        with pytest.raises(_StatusError):
            await invoke_model_with_retry(
                object(),
                [],
                invoke=invoke,
                settings=_ZERO_BACKOFF,
                retry_event_sink=sink,
            )

        assert calls == 5
        assert [event["attempt"] for event in events] == [2, 3, 4, 5]

    @pytest.mark.asyncio
    async def test_non_retryable_error_raises_without_events(self) -> None:
        events: list[dict[str, Any]] = []

        async def invoke(*args: Any, **kwargs: Any) -> AIMessage:
            raise _StatusError("invalid api key", 401)

        async def sink(payload: dict[str, Any]) -> None:
            events.append(payload)

        with pytest.raises(_StatusError):
            await invoke_model_with_retry(
                object(),
                [],
                invoke=invoke,
                settings=_ZERO_BACKOFF,
                retry_event_sink=sink,
            )

        assert events == []



    @pytest.mark.asyncio
    async def test_cancelled_error_propagates_without_retry(self) -> None:
        calls = 0

        async def invoke(*args: Any, **kwargs: Any) -> AIMessage:
            nonlocal calls
            calls += 1
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await invoke_model_with_retry(
                object(),
                [],
                invoke=invoke,
                settings=_ZERO_BACKOFF,
            )

        assert calls == 1
