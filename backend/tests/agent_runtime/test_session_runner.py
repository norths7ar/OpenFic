from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent_runtime.runner.session_runner import SessionRunner


@pytest.mark.asyncio
async def test_cancel_and_continue_queues_compiled_user_message():
    runner = SessionRunner(
        session_id="sess_cancel_001",
        task_id="task_cancel_001",
        model_config={
            "provider_type": "openai",
            "model_id": "gpt",
            "api_key": "k",
            "base_url": "",
            "max_context_tokens": 8000,
        },
        project_id="proj_001",
    )
    fake_session = MagicMock(close=AsyncMock())
    raw_message = '<of-mention chapter_id="chap_1" label="旧章节" />'

    with patch(
        "app.agent_runtime.runner.session_runner.create_session",
        AsyncMock(return_value=fake_session),
    ):
        await runner.cancel_and_continue(raw_message, "msg_cancel_001")

    assert runner._cancel_event.is_set()
    assert runner._inject_queue.get_nowait() == (
        None,
        "system",
        "[系统] 上一条回复被用户中止",
    )
    assert runner._inject_queue.get_nowait() == (
        "msg_cancel_001",
        "user",
        raw_message,
    )


@pytest.mark.asyncio
async def test_consume_next_pending_user_message_persists_and_removes_injected_item():
    runner = SessionRunner(
        session_id="sess_pending_continue_001",
        task_id="task_pending_continue_001",
        model_config={
            "provider_type": "openai",
            "model_id": "gpt",
            "api_key": "k",
            "base_url": "",
            "max_context_tokens": 8000,
        },
        project_id="proj_pending_continue_001",
    )
    created_at = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
    runner._queued_user_messages["msg_pending_1"] = ("压缩后继续处理", created_at)
    runner._queued_user_messages["msg_pending_2"] = ("下一条 pending", created_at)
    await runner._inject_queue.put((None, "system", "系统消息"))
    await runner._inject_queue.put(("msg_pending_1", "user", "压缩后继续处理"))
    await runner._inject_queue.put(("msg_pending_2", "user", "下一条 pending"))

    with (
        patch.object(
            runner,
            "_persist_user_message",
            AsyncMock(),
        ) as persist_user_message,
        patch.object(
            runner,
            "_emit_pending_user_message",
            AsyncMock(),
        ) as emit_pending_user_message,
        patch.object(
            runner,
            "_emit_runtime_user_message",
            AsyncMock(),
        ) as emit_runtime_user_message,
    ):
        result = await runner.consume_next_pending_user_message_for_continuation()

    assert result == ("msg_pending_1", "压缩后继续处理")
    persist_user_message.assert_awaited_once_with(
        "压缩后继续处理",
        message_id="msg_pending_1",
        created_at=created_at,
    )
    emit_pending_user_message.assert_awaited_once_with(
        "压缩后继续处理",
        message_id="msg_pending_1",
        action="consumed",
        created_at=created_at.isoformat(),
    )
    emit_runtime_user_message.assert_awaited_once_with(
        "压缩后继续处理",
        message_id="msg_pending_1",
        created_at=created_at.isoformat(),
    )
    assert "msg_pending_1" not in runner._queued_user_messages
    assert runner._queued_user_messages["msg_pending_2"] == (
        "下一条 pending",
        created_at,
    )

    remaining: list[tuple[str | None, str, str]] = []
    while not runner._inject_queue.empty():
        remaining.append(runner._inject_queue.get_nowait())
    assert remaining == [
        (None, "system", "系统消息"),
        ("msg_pending_2", "user", "下一条 pending"),
    ]


@pytest.mark.asyncio
async def test_consume_next_pending_user_message_keeps_pending_when_persist_fails():
    runner = SessionRunner(
        session_id="sess_pending_persist_error_001",
        task_id="task_pending_persist_error_001",
        model_config={
            "provider_type": "openai",
            "model_id": "gpt",
            "api_key": "k",
            "base_url": "",
            "max_context_tokens": 8000,
        },
        project_id="proj_pending_persist_error_001",
    )
    created_at = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
    runner._queued_user_messages["msg_pending_1"] = ("压缩后继续处理", created_at)
    await runner._inject_queue.put(("msg_pending_1", "user", "压缩后继续处理"))

    with (
        patch.object(
            runner,
            "_persist_user_message",
            AsyncMock(side_effect=RuntimeError("db write failed")),
        ),
        patch.object(
            runner,
            "_emit_pending_user_message",
            AsyncMock(),
        ) as emit_pending_user_message,
        patch.object(
            runner,
            "_emit_runtime_user_message",
            AsyncMock(),
        ) as emit_runtime_user_message,
    ):
        with pytest.raises(RuntimeError, match="db write failed"):
            await runner.consume_next_pending_user_message_for_continuation()

    assert runner._queued_user_messages["msg_pending_1"] == (
        "压缩后继续处理",
        created_at,
    )
    remaining: list[tuple[str | None, str, str]] = []
    while not runner._inject_queue.empty():
        remaining.append(runner._inject_queue.get_nowait())
    assert remaining == [("msg_pending_1", "user", "压缩后继续处理")]
    emit_pending_user_message.assert_not_awaited()
    emit_runtime_user_message.assert_not_awaited()
