"""Delivery boundaries and failed model attempts never execute partial work."""

from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessageChunk

from app.agent_runtime.persistence.persister import MessagePersister
from app.agent_runtime.runner.run_registry import AgentRunRegistry
from app.agent_runtime.runner.session_runner import SessionRunner
from app.api.routers import agent_runtime


def runner():
    item = SessionRunner(
        session_id="delivery-test", task_id="task", model_config={"max_context_tokens": 8000}
    )
    item._emit_pending_user_message = AsyncMock()
    item._persist_user_message = AsyncMock()
    item._emit_runtime_user_message = AsyncMock()
    return item


@pytest.mark.asyncio
async def test_queue_is_not_injected_and_stop_preserves_both_modes():
    item = runner()
    steer = await item.queue_pending_user_message("adjust", delivery_mode="steer")
    queued = await item.queue_pending_user_message("next", delivery_mode="queue")
    assert item._inject_queue.qsize() == 1
    assert item._inject_queue.get_nowait()[0] == steer["message_id"]
    item.cancel()
    assert [entry["delivery_mode"] for entry in item.list_pending_user_messages()] == [
        "steer",
        "queue",
    ]
    assert item._inject_queue.empty()
    await item.cancel_pending_user_message(queued["message_id"])
    assert len(item.list_pending_user_messages()) == 1


@pytest.mark.asyncio
async def test_boundary_receipt_is_once_and_only_after_persistence():
    item = runner()
    pending = await item.queue_pending_user_message("adjust")
    message_id = pending["message_id"]
    item._persist_user_message.side_effect = RuntimeError("write failed")
    with pytest.raises(RuntimeError):
        await item._mark_injected_user_message_sent(message_id)
    assert item.peek_next_pending_user_message() == (message_id, "adjust")
    assert item._emit_pending_user_message.await_args.kwargs["action"] == "queued"
    item._persist_user_message.side_effect = None
    assert await item._mark_injected_user_message_sent(message_id)
    assert not await item._mark_injected_user_message_sent(message_id)
    assert item._emit_pending_user_message.await_args.kwargs["action"] == "consumed"


@pytest.mark.asyncio
async def test_completed_run_consumes_queue_in_order_but_cancel_does_not(monkeypatch):
    item = runner()
    item.last_run_completed = True
    item.run = AsyncMock()
    registry = AgentRunRegistry()
    monkeypatch.setitem(agent_runtime._SESSION_RUNNERS, item.session_id, item)
    one = await item.queue_pending_user_message("one", delivery_mode="queue")
    two = await item.queue_pending_user_message("two", delivery_mode="queue")
    await agent_runtime._run_pending_continuations(item.session_id, registry)
    assert [call.kwargs["user_message_id"] for call in item.run.await_args_list] == [
        one["message_id"],
        two["message_id"],
    ]
    assert not item.list_pending_user_messages()
    await item.queue_pending_user_message("after stop", delivery_mode="queue")
    registry._cancelled_sessions.add(item.session_id)
    await agent_runtime._run_pending_continuations(item.session_id, registry)
    assert item.run.await_count == 2
    assert len(item.list_pending_user_messages()) == 1


@pytest.mark.asyncio
async def test_failed_attempt_discards_partial_tool_arguments_and_late_chunks():
    persister = MessagePersister("session", "task", "project", AsyncMock())
    persister._write = AsyncMock()
    await persister.handle({"event": "on_chat_model_start", "run_id": "attempt-1", "data": {}})
    chunk = AIMessageChunk(
        content="unfinished",
        tool_call_chunks=[
            {
                "id": "tool-1",
                "name": "propose_project_change",
                "args": '{"body":"partial',
                "index": 0,
            }
        ],
    )
    event = {"event": "on_chat_model_stream", "run_id": "attempt-1", "data": {"chunk": chunk}}
    await persister.handle(event)
    assert persister.discard_incomplete_attempts() == ["attempt-1"]
    await persister.handle(event)
    await persister.finalize("done")
    persister._write.assert_not_awaited()


@pytest.mark.asyncio
async def test_actual_langchain_retry_event_order_does_not_persist_failed_draft():
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    from langchain_core.messages import HumanMessage
    from langchain_core.runnables import RunnableLambda

    from app.agent_runtime.graph.llm_invoke import LLMInvokeSettings, invoke_model_with_retry
    from app.agent_runtime.graph.react_agent import _invoke_model
    from app.agent_runtime.runner.event_translator import EventTranslator

    class FailsOnce(FakeListChatModel):
        failed: bool = False

        async def _astream(self, *args, **kwargs):
            async for chunk in super()._astream(*args, **kwargs):
                yield chunk
                if not self.failed:
                    self.failed = True
                    raise ConnectionError("502 after partial output")

    model = FailsOnce(responses=["unfinished", "replacement"])
    persister = MessagePersister("session", "task", "project", AsyncMock())
    persister._write = AsyncMock()
    translator = EventTranslator("session")
    emitted = []

    async def retry_sink(_payload):
        discarded = persister.discard_incomplete_attempts()
        translator.discard_model_runs(discarded)
        emitted.append({"name": "agent:attempt_reset", "data": {"run_ids": discarded}})

    async def invoke(_input):
        return await invoke_model_with_retry(
            model,
            [HumanMessage(content="test")],
            invoke=_invoke_model,
            settings=LLMInvokeSettings(retry_base_interval=0),
            retry_event_sink=retry_sink,
        )

    async for event in RunnableLambda(invoke).astream_events({}, version="v2"):
        translated = translator.translate(event)
        if translated:
            emitted.extend(translated if isinstance(translated, list) else [translated])
        await persister.handle(event)
    await persister.finalize("done")
    contents = [call.kwargs.get("content") for call in persister._write.await_args_list]
    assert contents == ["replacement"]
    assert any(
        item["name"] == "agent:attempt_reset" and item["data"]["run_ids"] for item in emitted
    )


@pytest.mark.asyncio
async def test_withdraw_restores_uploaded_attachments():
    item = runner()
    attachments = [{"id": "image-1", "mime_type": "image/png", "url": "/agent-attachments/image-1"}]
    queued = await item.queue_pending_user_message(
        "image request", delivery_mode="queue", attachments=attachments
    )
    restored = await item.cancel_pending_user_message(queued["message_id"])
    assert restored["attachments"] == attachments
    assert not item.list_pending_user_messages()


@pytest.mark.asyncio
async def test_message_arriving_at_final_cleanup_is_launched_under_lifecycle_lock(monkeypatch):
    item = runner()
    item.last_run_completed = True
    registry = AgentRunRegistry()
    monkeypatch.setitem(agent_runtime._SESSION_RUNNERS, item.session_id, item)
    queued = await item.queue_pending_user_message("last boundary", delivery_mode="queue")
    launches = []

    async def launch(**kwargs):
        launches.append(kwargs)
        assert registry.session_lock(item.session_id).locked()
        kwargs["coro"].close()

    monkeypatch.setattr(agent_runtime, "_launch_task", launch)
    async with registry.session_lock(item.session_id):
        await agent_runtime._launch_pending_after_completion(
            session_id=item.session_id,
            registry=registry,
            db_session_factory=AsyncMock(),
            task_id=item.task_id,
            project_id=item.project_id,
        )
    assert len(launches) == 1
    assert launches[0]["lifecycle_lock_held"] is True
    assert launches[0]["clear_cancelled"] is False
    assert queued["message_id"] in item._received_user_message_ids
