"""Agent API 测试。"""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.agent_runtime.persistence import repo as message_repo
from app.agent_runtime.persistence.child_runs import (
    create_child_run,
    record_child_run_pending_approval,
)
from app.agent_runtime.persistence.model import AgentChildRunRequest
from app.agent_runtime.revisions import begin_user_revision
from app.agent_runtime.runner.checkpointer import reset_checkpointer
from app.agent_runtime.runner.run_registry import get_agent_run_registry
from app.agent_runtime.runner.session_runner import SessionRunner
from app.agent_runtime.streaming.replay_buffer import get_agent_event_replay_buffer
from app.api.routers.agent_runtime import (
    _SESSION_RUNNERS,
    _launch_task,
)
from app.socket.handlers import agent_subagents_room
from app.storage.models.revision import Revision
from app.storage.repos import revision_repo
from app.storage.services import task_service

pytestmark = pytest.mark.usefixtures("fast_checkpoint_sqlite")


@pytest_asyncio.fixture(autouse=True)
async def reset_agent_runtime_globals(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AGENT_CHECKPOINT_DB", str(tmp_path / "checkpoints.db"))
    await get_agent_run_registry().cancel_all()
    _SESSION_RUNNERS.clear()
    await reset_checkpointer()
    try:
        yield
    finally:
        await get_agent_run_registry().cancel_all()
        _SESSION_RUNNERS.clear()
        await reset_checkpointer()


async def _seed_agent_target(client: AsyncClient) -> dict[str, str]:
    project_response = await client.post(
        "/api/v1/projects",
        data={"title": "测试小说", "description": "一个关于冒险的故事"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]
    volumes_response = await client.get(f"/api/v1/projects/{project_id}/volumes")
    assert volumes_response.status_code == 200
    volume_id = volumes_response.json()[0]["id"]

    chapter_response = await client.post(
        f"/api/v1/projects/{project_id}/chapters",
        json={
            "volume_id": volume_id,
            "title": "第一章 开始",
            "content": "这是一个晴朗的早晨，主人公踏上了旅程。",
        },
    )
    assert chapter_response.status_code == 201
    chapter_id = chapter_response.json()["id"]

    provider_response = await client.post(
        "/api/v1/model-providers",
        data={
            "name": "测试提供商",
            "url": "https://api.test.com",
            "api_key": "test_api_key",
            "provider_type": "openai-compatible",
        },
    )
    assert provider_response.status_code == 201
    provider_id = provider_response.json()["id"]

    model_response = await client.post(
        "/api/v1/models",
        json={
            "name": "测试模型",
            "provider_id": provider_id,
            "model_id": "gpt-3.5-turbo",
            "temperature": 0.7,
            "max_tokens": 2000,
            "context_length": 8000,
        },
    )
    assert model_response.status_code == 201
    model_id = model_response.json()["id"]

    return {
        "project_id": project_id,
        "chapter_id": chapter_id,
        "provider_id": provider_id,
        "model_id": model_id,
    }


@pytest.mark.asyncio
class TestAgentAPI:


    async def test_get_session_state_hides_interrupts_after_session_cancelled(
        self,
        client: AsyncClient,
        session,
    ) -> None:
        target = await _seed_agent_target(client)
        session_response = await client.post(
            "/api/v1/agent/sessions",
            json={"project_id": target["project_id"], "model_id": target["model_id"]},
        )
        payload = session_response.json()
        session_id = payload["session_id"]
        task = await task_service.get_task(session, payload["task_id"])
        revision = Revision(
            project_id=task.project_id,
            task_id=task.id,
            message="cancelled approval",
            agent_session_id=session_id,
            revision_type="agent",
            status="cancelled",
            is_checkpoint=True,
            project_snapshot_title="Cancelled approval",
            project_snapshot_word_count=0,
            project_snapshot_chapter_count=0,
        )
        session.add(revision)
        await session.flush()
        task.current_revision_id = revision.id
        session.add(task)
        await session.commit()

        interrupt = SimpleNamespace(
            id="interrupt-approval-cancelled",
            value={"type": "tool_approval", "tool_name": "edit_note", "args": {}},
        )
        fake_checkpointer = SimpleNamespace(
            aget_tuple=AsyncMock(
                return_value=SimpleNamespace(
                    checkpoint={"channel_values": {"session_id": session_id}},
                    pending_writes=[("task-1", "__interrupt__", [interrupt])],
                )
            )
        )
        fake_registry = SimpleNamespace(is_running=AsyncMock(return_value=False))

        with (
            patch(
                "app.api.routers.agent_runtime.get_checkpointer",
                new=AsyncMock(return_value=fake_checkpointer),
            ),
            patch(
                "app.api.routers.agent_runtime.get_agent_run_registry",
                return_value=fake_registry,
            ),
        ):
            response = await client.get(f"/api/v1/agent/sessions/{session_id}")

            task.is_running = True
            session.add(task)
            await session.commit()
            fake_registry.is_running.return_value = True
            running_response = await client.get(f"/api/v1/agent/sessions/{session_id}")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["is_running"] is False
        assert response.json()["interrupts"] == []

        assert running_response.status_code == status.HTTP_200_OK
        assert running_response.json()["is_running"] is True
        assert running_response.json()["interrupts"] == []
        assert fake_registry.is_running.await_count == 2

    async def test_tool_approval_does_not_resume_cancelled_session(
        self,
        client: AsyncClient,
        session,
    ) -> None:
        target = await _seed_agent_target(client)
        session_response = await client.post(
            "/api/v1/agent/sessions",
            json={"project_id": target["project_id"], "model_id": target["model_id"]},
        )
        payload = session_response.json()
        session_id = payload["session_id"]
        task = await task_service.get_task(session, payload["task_id"])
        revision = Revision(
            project_id=task.project_id,
            task_id=task.id,
            message="cancelled approval",
            agent_session_id=session_id,
            revision_type="agent",
            status="cancelled",
            is_checkpoint=True,
            project_snapshot_title="Cancelled approval",
            project_snapshot_word_count=0,
            project_snapshot_chapter_count=0,
        )
        session.add(revision)
        await session.flush()
        task.current_revision_id = revision.id
        session.add(task)
        await session.commit()

        with patch("app.api.routers.agent_runtime._launch_task", new=AsyncMock()) as launch_task:
            response = await client.post(
                f"/api/v1/agent/sessions/{session_id}/tool-approval",
                json={"approval_id": "interrupt-approval-cancelled", "approved": False},
            )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["detail"]["code"] == "session_cancelled"
        launch_task.assert_not_awaited()

    async def test_manual_compaction_does_not_resume_cancelled_session(
        self,
        client: AsyncClient,
        session,
    ) -> None:
        target = await _seed_agent_target(client)
        session_response = await client.post(
            "/api/v1/agent/sessions",
            json={"project_id": target["project_id"], "model_id": target["model_id"]},
        )
        payload = session_response.json()
        session_id = payload["session_id"]
        task = await task_service.get_task(session, payload["task_id"])
        revision = Revision(
            project_id=task.project_id,
            task_id=task.id,
            message="cancelled compaction",
            agent_session_id=session_id,
            revision_type="agent",
            status="cancelled",
            is_checkpoint=True,
            project_snapshot_title="Cancelled compaction",
            project_snapshot_word_count=0,
            project_snapshot_chapter_count=0,
        )
        session.add(revision)
        await session.flush()
        task.current_revision_id = revision.id
        task.is_running = False
        session.add(task)
        await session.commit()

        runner = _SESSION_RUNNERS[session_id]
        with patch.object(runner, "compact", new=AsyncMock()) as compact:
            response = await client.post(f"/api/v1/agent/sessions/{session_id}/compaction")

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["detail"]["code"] == "session_cancelled"
        compact.assert_not_awaited()


    async def test_runner_finalizer_does_not_overwrite_cancelled_revision(
        self,
        client: AsyncClient,
        session,
    ) -> None:
        target = await _seed_agent_target(client)
        session_response = await client.post(
            "/api/v1/agent/sessions",
            json={"project_id": target["project_id"], "model_id": target["model_id"]},
        )
        payload = session_response.json()
        task = await task_service.get_task(session, payload["task_id"])
        revision = Revision(
            project_id=task.project_id,
            task_id=task.id,
            message="cancelled revision",
            agent_session_id=payload["session_id"],
            revision_type="agent",
            status="cancelled",
            is_checkpoint=True,
            project_snapshot_title="Cancelled revision",
            project_snapshot_word_count=0,
            project_snapshot_chapter_count=0,
        )
        session.add(revision)
        await session.flush()

        finalized = await revision_repo.update_status_unless_cancelled(
            session,
            revision.id,
            "completed",
        )
        await session.commit()
        await session.refresh(revision)

        assert finalized is False
        assert revision.status == "cancelled"

    async def test_cancellation_does_not_overwrite_terminal_revision(
        self,
        client: AsyncClient,
        session,
    ) -> None:
        target = await _seed_agent_target(client)
        session_response = await client.post(
            "/api/v1/agent/sessions",
            json={"project_id": target["project_id"], "model_id": target["model_id"]},
        )
        payload = session_response.json()
        task = await task_service.get_task(session, payload["task_id"])
        revision = Revision(
            project_id=task.project_id,
            task_id=task.id,
            message="completed revision",
            agent_session_id=payload["session_id"],
            revision_type="agent",
            status="completed",
            is_checkpoint=True,
            project_snapshot_title="Completed revision",
            project_snapshot_word_count=0,
            project_snapshot_chapter_count=0,
        )
        session.add(revision)
        await session.flush()

        cancelled = await revision_repo.cancel_active_or_interrupted_revision(session, revision.id)

        await session.commit()
        await session.refresh(revision)
        assert cancelled is False
        assert revision.status == "completed"


    async def test_cancel_session_cascades_to_nested_subagent_sessions_without_deactivating_them(
        self,
        client: AsyncClient,
        session,
    ) -> None:
        target = await _seed_agent_target(client)
        session_response = await client.post(
            "/api/v1/agent/sessions",
            json={
                "project_id": target["project_id"],
                "model_id": target["model_id"],
                "max_iterations": 5,
            },
        )
        payload = session_response.json()
        parent_session_id = payload["session_id"]
        task_id = payload["task_id"]

        child = await create_child_run(
            session,
            parent_session_id=parent_session_id,
            parent_task_id=task_id,
            parent_thread_id=parent_session_id,
            child_thread_id=f"{parent_session_id}:child:parent",
            agent_key="writer",
            dispatch_id="dispatch-parent",
            tool_call_id="tool-call-parent",
            request={"task": "write", "input": {}, "metadata": {}},
            status="running",
        )
        nested_child = await create_child_run(
            session,
            parent_session_id=child.child_thread_id,
            parent_task_id=task_id,
            parent_thread_id=child.child_thread_id,
            child_thread_id=f"{child.child_thread_id}:child:nested",
            agent_key="reviewer",
            dispatch_id="dispatch-nested",
            tool_call_id="tool-call-nested",
            request={"task": "review", "input": {}, "metadata": {}},
            status="running",
        )

        fake_registry = SimpleNamespace(
            cancel=AsyncMock(return_value=True),
            mark_cancelled=AsyncMock(return_value=None),
            cancel_task=AsyncMock(return_value=False),
            clear_cancelled=AsyncMock(),
            register=AsyncMock(),
            unregister=AsyncMock(return_value=True),
            is_running=AsyncMock(return_value=False),
            is_parent_running=AsyncMock(return_value=False),
        )

        with (
            patch.object(_SESSION_RUNNERS[parent_session_id], "cancel") as runner_cancel,
            patch(
                "app.api.routers.agent_runtime.get_agent_run_registry",
                return_value=fake_registry,
            ),
        ):
            response = await client.post(f"/api/v1/agent/sessions/{parent_session_id}/cancel")

        assert response.status_code == status.HTTP_200_OK
        runner_cancel.assert_called_once_with()
        cancelled_session_ids = [item.args[0] for item in fake_registry.cancel.await_args_list]
        assert {
            parent_session_id,
            child.child_thread_id,
        }.issubset(set(cancelled_session_ids))

        parent_children = await client.get(f"/api/v1/agent/sessions/{parent_session_id}/subagents")
        nested_children = await client.get(
            f"/api/v1/agent/sessions/{child.child_thread_id}/subagents"
        )
        assert parent_children.status_code == status.HTTP_200_OK
        assert nested_children.status_code == status.HTTP_200_OK
        assert parent_children.json() == [
            {
                "child_run_id": child.id,
                "child_thread_id": child.child_thread_id,
                "agent_key": "writer",
                "agent_number": child.metadata_json["agent_number"],
                "status": "cancelled",
                "queued_messages": 0,
                "is_active": True,
                "pending_approval": None,
            },
        ]
        assert nested_children.json() == [
            {
                "child_run_id": nested_child.id,
                "child_thread_id": nested_child.child_thread_id,
                "agent_key": "reviewer",
                "agent_number": nested_child.metadata_json["agent_number"],
                "status": "cancelled",
                "queued_messages": 0,
                "is_active": True,
                "pending_approval": None,
            },
        ]

    async def test_cancel_session_keeps_completed_subagent_status_unchanged(
        self,
        client: AsyncClient,
        session,
    ) -> None:
        target = await _seed_agent_target(client)
        session_response = await client.post(
            "/api/v1/agent/sessions",
            json={
                "project_id": target["project_id"],
                "model_id": target["model_id"],
                "max_iterations": 5,
            },
        )
        payload = session_response.json()
        parent_session_id = payload["session_id"]
        task_id = payload["task_id"]

        completed_child = await create_child_run(
            session,
            parent_session_id=parent_session_id,
            parent_task_id=task_id,
            parent_thread_id=parent_session_id,
            child_thread_id=f"{parent_session_id}:child:completed",
            agent_key="writer",
            dispatch_id="dispatch-completed",
            tool_call_id="tool-call-completed",
            request={"task": "write", "input": {}, "metadata": {}},
            status="completed",
        )
        running_child = await create_child_run(
            session,
            parent_session_id=parent_session_id,
            parent_task_id=task_id,
            parent_thread_id=parent_session_id,
            child_thread_id=f"{parent_session_id}:child:running",
            agent_key="reviewer",
            dispatch_id="dispatch-running",
            tool_call_id="tool-call-running",
            request={"task": "review", "input": {}, "metadata": {}},
            status="running",
        )

        fake_registry = SimpleNamespace(
            cancel=AsyncMock(return_value=True),
            mark_cancelled=AsyncMock(return_value=None),
            cancel_task=AsyncMock(return_value=False),
            clear_cancelled=AsyncMock(),
            register=AsyncMock(),
            unregister=AsyncMock(return_value=True),
            is_running=AsyncMock(return_value=False),
            is_parent_running=AsyncMock(return_value=False),
        )

        with (
            patch.object(_SESSION_RUNNERS[parent_session_id], "cancel") as runner_cancel,
            patch(
                "app.api.routers.agent_runtime.get_agent_run_registry",
                return_value=fake_registry,
            ),
        ):
            response = await client.post(f"/api/v1/agent/sessions/{parent_session_id}/cancel")

        assert response.status_code == status.HTTP_200_OK
        runner_cancel.assert_called_once_with()

        await session.refresh(completed_child)
        await session.refresh(running_child)
        assert completed_child.status == "completed"
        assert running_child.status == "cancelled"

        children_response = await client.get(
            f"/api/v1/agent/sessions/{parent_session_id}/subagents"
        )
        assert children_response.status_code == status.HTTP_200_OK
        assert children_response.json() == [
            {
                "child_run_id": completed_child.id,
                "child_thread_id": completed_child.child_thread_id,
                "agent_key": "writer",
                "agent_number": completed_child.metadata_json["agent_number"],
                "status": "completed",
                "queued_messages": 0,
                "is_active": True,
                "pending_approval": None,
            },
            {
                "child_run_id": running_child.id,
                "child_thread_id": running_child.child_thread_id,
                "agent_key": "reviewer",
                "agent_number": running_child.metadata_json["agent_number"],
                "status": "cancelled",
                "queued_messages": 0,
                "is_active": True,
                "pending_approval": None,
            },
        ]

    async def test_cancel_session_publishes_cancelled_subagent_status_to_parent_stream(
        self,
        client: AsyncClient,
        session,
    ) -> None:
        buffer = get_agent_event_replay_buffer()
        buffer.clear_all()
        try:
            target = await _seed_agent_target(client)
            session_response = await client.post(
                "/api/v1/agent/sessions",
                json={
                    "project_id": target["project_id"],
                    "model_id": target["model_id"],
                    "max_iterations": 5,
                },
            )
            payload = session_response.json()
            parent_session_id = payload["session_id"]
            task_id = payload["task_id"]

            child = await create_child_run(
                session,
                parent_session_id=parent_session_id,
                parent_task_id=task_id,
                parent_thread_id=parent_session_id,
                child_thread_id=f"{parent_session_id}:child:parent",
                agent_key="writer",
                dispatch_id="dispatch-parent",
                tool_call_id="tool-call-parent",
                request={"task": "write", "input": {}, "metadata": {}},
                status="running",
            )

            fake_registry = SimpleNamespace(
                cancel=AsyncMock(return_value=True),
                mark_cancelled=AsyncMock(return_value=None),
                cancel_task=AsyncMock(return_value=False),
                clear_cancelled=AsyncMock(),
                register=AsyncMock(),
                unregister=AsyncMock(return_value=True),
                is_running=AsyncMock(return_value=False),
                is_parent_running=AsyncMock(return_value=False),
            )
            emit_mock = AsyncMock()

            with (
                patch.object(
                    _SESSION_RUNNERS[parent_session_id],
                    "cancel",
                ) as runner_cancel,
                patch(
                    "app.api.routers.agent_runtime.get_agent_run_registry",
                    return_value=fake_registry,
                ),
                patch(
                    "app.api.routers.agent_runtime.emit",
                    new=emit_mock,
                ),
                patch(
                    "app.agent_runtime.runner.subagent_runner.emit",
                    new=emit_mock,
                ),
            ):
                response = await client.post(f"/api/v1/agent/sessions/{parent_session_id}/cancel")

            assert response.status_code == status.HTTP_200_OK
            runner_cancel.assert_called_once_with()

            replayed = buffer.replay_events_unlocked(parent_session_id)
            cancelled_statuses = [
                event.data
                for event in replayed
                if event.name == "agent:subagent_status"
                and event.data.get("child_run_id") == child.id
            ]
            assert cancelled_statuses == [
                {
                    "parent_session_id": parent_session_id,
                    "child_run_id": child.id,
                    "child_thread_id": child.child_thread_id,
                    "agent_key": "writer",
                    "agent_number": child.metadata_json["agent_number"],
                    "status": "cancelled",
                    "queued_messages": 0,
                    "is_active": True,
                    "pending_approval": None,
                }
            ]
            emit_mock.assert_any_await(
                "agent:subagent_status",
                cancelled_statuses[0],
                room=agent_subagents_room(parent_session_id),
            )
        finally:
            buffer.clear_all()

    async def test_cancel_subagent_session_cancels_child_task_and_marks_cancelled(
        self,
        client: AsyncClient,
        session,
    ) -> None:
        target = await _seed_agent_target(client)
        session_response = await client.post(
            "/api/v1/agent/sessions",
            json={
                "project_id": target["project_id"],
                "model_id": target["model_id"],
                "max_iterations": 5,
            },
        )
        payload = session_response.json()
        parent_session_id = payload["session_id"]
        task_id = payload["task_id"]

        child = await create_child_run(
            session,
            parent_session_id=parent_session_id,
            parent_task_id=task_id,
            parent_thread_id=parent_session_id,
            child_thread_id=f"{parent_session_id}:child:cancel",
            agent_key="writer",
            dispatch_id="dispatch-cancel",
            tool_call_id="tool-call-cancel",
            request={"task": "write", "input": {}, "metadata": {}},
            status="running",
        )

        task_started = asyncio.Event()
        task_finished = asyncio.Event()

        async def fake_child() -> None:
            task_started.set()
            try:
                await asyncio.sleep(60)
            finally:
                task_finished.set()

        child_task = asyncio.create_task(fake_child())
        await get_agent_run_registry().register_child(parent_session_id, child.id, child_task)
        try:
            await task_started.wait()

            emit_mock = AsyncMock()
            with (
                patch(
                    "app.api.routers.agent_runtime.emit",
                    new=emit_mock,
                ),
                patch(
                    "app.agent_runtime.runner.subagent_runner.emit",
                    new=emit_mock,
                ),
            ):
                response = await client.post(
                    f"/api/v1/agent/sessions/{parent_session_id}/subagents/{child.id}/cancel"
                )

            assert response.status_code == status.HTTP_200_OK
            assert response.json()["success"] is True

            await asyncio.wait_for(task_finished.wait(), timeout=2)
            assert child_task.cancelled() is True

            await session.refresh(child)
            assert child.status == "cancelled"
            assert child.is_active is True
            assert child.error == "user cancelled subagent"

            request_row = (
                await session.execute(
                    select(AgentChildRunRequest).where(
                        AgentChildRunRequest.child_run_id == child.id
                    )
                )
            ).scalar_one()
            assert request_row.status == "cancelled"
            assert request_row.error == "user cancelled subagent"
        finally:
            await get_agent_run_registry().unregister_child(parent_session_id, child.id)

    async def test_cancel_subagent_session_returns_404_for_unknown_child(
        self,
        client: AsyncClient,
        session,
    ) -> None:
        response = await client.post(
            "/api/v1/agent/sessions/unknown-parent/subagents/unknown-child/cancel"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_cancel_subagent_session_is_noop_for_terminal_child(
        self,
        client: AsyncClient,
        session,
    ) -> None:
        target = await _seed_agent_target(client)
        session_response = await client.post(
            "/api/v1/agent/sessions",
            json={
                "project_id": target["project_id"],
                "model_id": target["model_id"],
                "max_iterations": 5,
            },
        )
        payload = session_response.json()
        parent_session_id = payload["session_id"]
        task_id = payload["task_id"]

        child = await create_child_run(
            session,
            parent_session_id=parent_session_id,
            parent_task_id=task_id,
            parent_thread_id=parent_session_id,
            child_thread_id=f"{parent_session_id}:child:terminal",
            agent_key="writer",
            dispatch_id="dispatch-terminal",
            tool_call_id="tool-call-terminal",
            request={"task": "write", "input": {}, "metadata": {}},
            status="completed",
        )

        response = await client.post(
            f"/api/v1/agent/sessions/{parent_session_id}/subagents/{child.id}/cancel"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True

        await session.refresh(child)
        assert child.status == "completed"
        assert child.error is None

    async def test_cancel_session_starts_new_run_after_cancelled_revision(
        self,
        client: AsyncClient,
        session,
    ) -> None:
        target = await _seed_agent_target(client)
        session_response = await client.post(
            "/api/v1/agent/sessions",
            json={
                "project_id": target["project_id"],
                "model_id": target["model_id"],
                "max_iterations": 5,
            },
        )
        payload = session_response.json()
        session_id = payload["session_id"]
        task_id = payload["task_id"]

        user_message = await message_repo.insert_message(
            session,
            session_id=session_id,
            task_id=task_id,
            project_id=target["project_id"],
            role="user",
            status="sent",
            content="继续处理当前问题",
        )
        revision = await begin_user_revision(
            session,
            project_id=target["project_id"],
            task_id=task_id,
            agent_session_id=session_id,
            user_message_id=user_message.id,
            user_message_seq=user_message.seq,
            message="用户消息: 继续处理当前问题",
            pre_run_checkpoint_id="cp-before-cancelled-run",
            graph_thread_id=session_id,
        )
        revision.status = "cancelled"
        session.add(revision)
        await session.commit()

        fake_registry = SimpleNamespace(
            cancel=AsyncMock(return_value=True),
            mark_cancelled=AsyncMock(return_value=None),
            cancel_task=AsyncMock(return_value=False),
            clear_cancelled=AsyncMock(),
            register=AsyncMock(),
            unregister=AsyncMock(return_value=True),
            is_running=AsyncMock(return_value=False),
            is_parent_running=AsyncMock(return_value=False),
        )
        with (
            patch(
                "app.api.routers.agent_runtime.get_agent_run_registry",
                return_value=fake_registry,
            ),
            patch(
                "app.api.routers.agent_runtime.SessionRunner.run",
                new=AsyncMock(return_value=None),
            ) as mock_run,
        ):
            cancel_response = await client.post(f"/api/v1/agent/sessions/{session_id}/cancel")
            assert cancel_response.status_code == status.HTTP_200_OK

            response = await client.post(
                f"/api/v1/agent/sessions/{session_id}/message",
                json={"message": "取消上一轮后重新开始"},
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True
        await asyncio.sleep(0.05)
        mock_run.assert_awaited_once_with(user_request="取消上一轮后重新开始")

    async def test_cancel_does_not_cancel_run_waiting_to_start(
        self,
        client: AsyncClient,
        session,
    ) -> None:
        target = await _seed_agent_target(client)
        session_response = await client.post(
            "/api/v1/agent/sessions",
            json={
                "project_id": target["project_id"],
                "model_id": target["model_id"],
                "max_iterations": 5,
            },
        )
        payload = session_response.json()
        session_id = payload["session_id"]
        task = await task_service.get_task(session, payload["task_id"])
        revision = Revision(
            project_id=task.project_id,
            task_id=task.id,
            message="active revision",
            agent_session_id=session_id,
            revision_type="agent",
            status="active",
            is_checkpoint=True,
            project_snapshot_title="Active revision",
            project_snapshot_word_count=0,
            project_snapshot_chapter_count=0,
        )
        session.add(revision)
        await session.flush()
        task.current_revision_id = revision.id
        session.add(task)
        await session.commit()

        finalize_entered = asyncio.Event()
        release_finalize = asyncio.Event()
        emit_entered = asyncio.Event()
        release_emit = asyncio.Event()
        run_started = asyncio.Event()
        release_run = asyncio.Event()
        run_saw_cancel = False
        runner = _SESSION_RUNNERS[session_id]

        async def block_finalize(*args: Any, **kwargs: Any) -> None:
            finalize_entered.set()
            await release_finalize.wait()

        async def fake_run(self: SessionRunner, *, user_request: str, **kwargs: Any) -> None:
            nonlocal run_saw_cancel
            self._cancel_event.clear()
            run_started.set()
            await release_run.wait()
            run_saw_cancel = self._cancel_event.is_set()

        async def block_cancel_notification(
            event_name: str, payload: dict[str, Any], **kwargs: Any
        ) -> None:
            if payload.get("is_running") is False:
                emit_entered.set()
                await release_emit.wait()

        with (
            patch(
                "app.api.routers.agent_runtime.finalize_revision_status",
                new=block_finalize,
            ),
            patch(
                "app.api.routers.agent_runtime.SessionRunner.run",
                new=fake_run,
            ),
            patch(
                "app.api.routers.agent_runtime.emit",
                new=block_cancel_notification,
            ),
        ):
            cancel_task = asyncio.create_task(
                client.post(f"/api/v1/agent/sessions/{session_id}/cancel")
            )
            await finalize_entered.wait()
            send_task = asyncio.create_task(
                client.post(
                    f"/api/v1/agent/sessions/{session_id}/message",
                    json={"message": "start after cancel"},
                )
            )
            await asyncio.sleep(0.05)
            assert not run_started.is_set()
            assert not send_task.done()

            release_finalize.set()
            await emit_entered.wait()
            await asyncio.sleep(0.05)
            assert not run_started.is_set()

            release_emit.set()
            cancel_response = await cancel_task
            send_response = await send_task
            assert cancel_response.status_code == status.HTTP_200_OK
            assert send_response.status_code == status.HTTP_200_OK
            await run_started.wait()
            release_run.set()
            await asyncio.sleep(0.05)

        assert run_saw_cancel is False
        assert runner._cancel_event.is_set() is False

    async def test_launch_task_returns_when_cancelled_before_start(self) -> None:
        registry = get_agent_run_registry()
        state_update_entered = asyncio.Event()
        release_state_update = asyncio.Event()

        async def block_state_update(**kwargs: Any) -> None:
            state_update_entered.set()
            await release_state_update.wait()

        async def should_not_run() -> None:
            raise AssertionError("cancelled task must not enter its coroutine")

        launch_task = asyncio.create_task(
            _launch_task(
                db_session_factory=lambda: None,
                session_id="launch-race",
                task_id="task-id",
                project_id="project-id",
                coro=should_not_run(),
            )
        )
        try:
            with patch(
                "app.api.routers.agent_runtime._set_task_running_state",
                new=block_state_update,
            ):
                await asyncio.wait_for(state_update_entered.wait(), timeout=1)
                assert await registry.cancel("launch-race") is True
                release_state_update.set()
                await asyncio.wait_for(launch_task, timeout=1)
        finally:
            release_state_update.set()
            if not launch_task.done():
                launch_task.cancel()
            await asyncio.gather(launch_task, return_exceptions=True)

        assert await registry.is_running("launch-race") is False

    async def test_cancel_succeeds_when_post_commit_cleanup_fails(
        self,
        client: AsyncClient,
        session,
    ) -> None:
        target = await _seed_agent_target(client)
        session_response = await client.post(
            "/api/v1/agent/sessions",
            json={
                "project_id": target["project_id"],
                "model_id": target["model_id"],
                "max_iterations": 5,
            },
        )
        payload = session_response.json()
        session_id = payload["session_id"]
        task = await task_service.get_task(session, payload["task_id"])
        revision = Revision(
            project_id=task.project_id,
            task_id=task.id,
            message="active revision",
            agent_session_id=session_id,
            revision_type="agent",
            status="active",
            is_checkpoint=True,
            project_snapshot_title="Active revision",
            project_snapshot_word_count=0,
            project_snapshot_chapter_count=0,
        )
        session.add(revision)
        await session.flush()
        task.current_revision_id = revision.id
        session.add(task)
        await session.commit()

        registry = get_agent_run_registry()
        parent_task = asyncio.create_task(asyncio.Event().wait())
        await registry.register(session_id, parent_task)

        with (
            patch(
                "app.api.routers.agent_runtime._cancel_subagent_session_tree",
                new=AsyncMock(side_effect=RuntimeError("cleanup failed")),
            ),
            patch(
                "app.api.routers.agent_runtime.emit",
                new=AsyncMock(side_effect=RuntimeError("notification failed")),
            ),
        ):
            response = await client.post(f"/api/v1/agent/sessions/{session_id}/cancel")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True
        await session.refresh(task)
        await session.refresh(revision)
        assert task.is_running is False
        assert revision.status == "cancelled"
        await asyncio.gather(parent_task, return_exceptions=True)
        assert parent_task.cancelled()

    async def test_send_does_not_queue_after_concurrent_cancellation(
        self,
        client: AsyncClient,
        session,
    ) -> None:
        target = await _seed_agent_target(client)
        session_response = await client.post(
            "/api/v1/agent/sessions",
            json={
                "project_id": target["project_id"],
                "model_id": target["model_id"],
                "max_iterations": 5,
            },
        )
        payload = session_response.json()
        session_id = payload["session_id"]
        task = await task_service.get_task(session, payload["task_id"])
        revision = Revision(
            project_id=task.project_id,
            task_id=task.id,
            message="active revision",
            agent_session_id=session_id,
            revision_type="agent",
            status="active",
            is_checkpoint=True,
            project_snapshot_title="Active revision",
            project_snapshot_word_count=0,
            project_snapshot_chapter_count=0,
        )
        session.add(revision)
        await session.flush()
        task.current_revision_id = revision.id
        session.add(task)
        await session.commit()

        registry = get_agent_run_registry()
        parent_task = asyncio.create_task(asyncio.Event().wait())
        await registry.register(session_id, parent_task)
        runner = _SESSION_RUNNERS[session_id]
        finalize_entered = asyncio.Event()
        release_finalize = asyncio.Event()

        async def block_finalize(*args: Any, **kwargs: Any) -> None:
            finalize_entered.set()
            await release_finalize.wait()

        queue_message = AsyncMock(
            return_value={
                "message_id": "should-not-queue",
                "content": "消息",
                "created_at": "2026-06-12T00:00:00+00:00",
            }
        )
        launch_task = AsyncMock(side_effect=lambda **kwargs: kwargs["coro"].close())
        cancel_request = None
        send_request = None
        try:
            with (
                patch(
                    "app.api.routers.agent_runtime.finalize_revision_status",
                    new=block_finalize,
                ),
                patch.object(runner, "queue_pending_user_message", new=queue_message),
                patch(
                    "app.api.routers.agent_runtime.SessionRunner.run",
                    new=AsyncMock(return_value=None),
                ),
                patch("app.api.routers.agent_runtime._launch_task", new=launch_task),
                patch(
                    "app.api.routers.agent_runtime._cancel_subagent_session_tree",
                    new=AsyncMock(),
                ),
                patch("app.api.routers.agent_runtime.emit", new=AsyncMock()),
            ):
                cancel_request = asyncio.create_task(
                    client.post(f"/api/v1/agent/sessions/{session_id}/cancel")
                )
                await asyncio.wait_for(finalize_entered.wait(), timeout=1)

                send_request = asyncio.create_task(
                    client.post(
                        f"/api/v1/agent/sessions/{session_id}/message",
                        json={"message": "并发消息"},
                    )
                )
                await asyncio.sleep(0.05)
                assert not send_request.done()
                queue_message.assert_not_awaited()

                release_finalize.set()
                cancel_response = await cancel_request
                send_response = await send_request

            assert cancel_response.status_code == status.HTTP_200_OK
            assert send_response.status_code == status.HTTP_200_OK
            queue_message.assert_not_awaited()
            launch_task.assert_awaited_once()
        finally:
            release_finalize.set()
            pending_requests = [request for request in (cancel_request, send_request) if request]
            for request in pending_requests:
                if not request.done():
                    request.cancel()
            await asyncio.gather(*pending_requests, return_exceptions=True)
            if not parent_task.done():
                parent_task.cancel()
            await asyncio.gather(parent_task, return_exceptions=True)


    async def test_cancel_pending_message_restores_message_content(
        self,
        client: AsyncClient,
    ) -> None:
        target = await _seed_agent_target(client)
        session_response = await client.post(
            "/api/v1/agent/sessions",
            json={
                "project_id": target["project_id"],
                "model_id": target["model_id"],
                "max_iterations": 5,
            },
        )
        session_id = session_response.json()["session_id"]
        runner = _SESSION_RUNNERS[session_id]

        with patch.object(
            runner,
            "cancel_pending_user_message",
            AsyncMock(
                return_value={
                    "message_id": "msg_pending_1",
                    "content": "补充要求：保留上一段语气",
                    "created_at": "2026-06-12T00:00:00+00:00",
                }
            ),
            create=True,
        ) as mock_cancel:
            response = await client.post(
                f"/api/v1/agent/sessions/{session_id}/pending-message/cancel",
                json={"message_id": "msg_pending_1"},
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "success": True,
            "session_id": session_id,
            "message_id": "msg_pending_1",
            "restored_message_content": "补充要求：保留上一段语气",
        }
        mock_cancel.assert_awaited_once_with("msg_pending_1")

    async def test_submit_tool_approval_launches_resume(self, client: AsyncClient) -> None:
        target = await _seed_agent_target(client)
        session_response = await client.post(
            "/api/v1/agent/sessions",
            json={
                "project_id": target["project_id"],
                "model_id": target["model_id"],
                "max_iterations": 5,
            },
        )
        session_id = session_response.json()["session_id"]

        with patch(
            "app.api.routers.agent_runtime.SessionRunner.resume", new=AsyncMock(return_value=None)
        ) as mock_resume:
            response = await client.post(
                f"/api/v1/agent/sessions/{session_id}/tool-approval",
                json={"approval_id": "approval-1", "approved": True},
            )

            assert response.status_code == status.HTTP_200_OK
            assert response.json()["success"] is True
            await asyncio.sleep(0.05)
            mock_resume.assert_awaited_once_with(
                {
                    "action_type": "tool_approval",
                    "approval_id": "approval-1",
                    "approved": True,
                }
            )

    async def test_submit_tool_approval_routes_idle_child_approval_to_subagent_resume(
        self,
        client: AsyncClient,
        session,
    ) -> None:
        target = await _seed_agent_target(client)
        session_response = await client.post(
            "/api/v1/agent/sessions",
            json={
                "project_id": target["project_id"],
                "model_id": target["model_id"],
                "max_iterations": 5,
            },
        )
        payload = session_response.json()
        session_id = payload["session_id"]
        task_id = payload["task_id"]
        row = await create_child_run(
            session,
            parent_session_id=session_id,
            parent_task_id=task_id,
            parent_thread_id=session_id,
            child_thread_id=f"{session_id}:child:approval",
            agent_key="writer",
            dispatch_id="dispatch-child",
            tool_call_id="tool-call-child",
            request={"task": "write", "input": {}, "metadata": {}},
            status="waiting_user",
        )
        await record_child_run_pending_approval(
            session,
            row.id,
            approval_id="approval-child-api",
            approval_request={
                "type": "tool_approval",
                "approval_id": "approval-child-api",
                "child_run_id": row.id,
            },
        )
        task = await task_service.get_task(session, task_id)
        revision = Revision(
            project_id=task.project_id,
            task_id=task.id,
            message="active parent revision",
            agent_session_id=session_id,
            revision_type="agent",
            status="active",
            is_checkpoint=True,
            project_snapshot_title="Active parent revision",
            project_snapshot_word_count=0,
            project_snapshot_chapter_count=0,
        )
        session.add(revision)
        await session.flush()
        task.current_revision_id = revision.id
        session.add(task)
        await session.commit()

        with (
            patch(
                "app.api.routers.agent_runtime.SessionRunner.resume",
                new=AsyncMock(return_value=None),
            ) as mock_parent_resume,
            patch(
                "app.api.routers.agent_runtime._launch_task",
                new=AsyncMock(
                    side_effect=AssertionError("child approvals must not launch a parent task")
                ),
            ) as mock_launch_task,
            patch(
                "app.api.routers.agent_runtime.ensure_child_processing",
                new=AsyncMock(return_value=True),
            ) as mock_ensure_child_processing,
        ):
            response = await client.post(
                f"/api/v1/agent/sessions/{session_id}/tool-approval",
                json={"approval_id": "approval-child-api", "approved": True},
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True
        mock_ensure_child_processing.assert_awaited_once()
        assert mock_ensure_child_processing.await_args is not None
        ensure_kwargs = mock_ensure_child_processing.await_args.kwargs
        assert ensure_kwargs["parent_session_id"] == session_id
        assert ensure_kwargs["child_run_id"] == row.id
        assert ensure_kwargs["resume_payload"] == {
            "action_type": "tool_approval",
            "approval_id": "approval-child-api",
            "approved": True,
        }
        assert type(ensure_kwargs["runner"]).__name__ == "SubagentRunner"
        mock_launch_task.assert_not_awaited()
        mock_parent_resume.assert_not_awaited()

    async def test_submit_tool_approval_routes_sync_child_approval_to_subagent_processing(
        self,
        client: AsyncClient,
        session,
    ) -> None:
        target = await _seed_agent_target(client)
        session_response = await client.post(
            "/api/v1/agent/sessions",
            json={
                "project_id": target["project_id"],
                "model_id": target["model_id"],
                "max_iterations": 5,
            },
        )
        payload = session_response.json()
        session_id = payload["session_id"]
        task_id = payload["task_id"]
        row = await create_child_run(
            session,
            parent_session_id=session_id,
            parent_task_id=task_id,
            parent_thread_id=session_id,
            child_thread_id=f"{session_id}:child:sync-approval",
            agent_key="composer",
            dispatch_id="dispatch-child-sync",
            tool_call_id="tool-call-child-sync",
            request={"task": "make a plan", "input": {}, "metadata": {}},
            status="waiting_user",
        )
        await record_child_run_pending_approval(
            session,
            row.id,
            approval_id="approval-child-sync-api",
            approval_request={
                "type": "tool_approval",
                "approval_id": "approval-child-sync-api",
                "child_run_id": row.id,
            },
        )

        with (
            patch(
                "app.api.routers.agent_runtime._launch_task",
                new=AsyncMock(
                    side_effect=AssertionError("sync child approvals must not launch a parent task")
                ),
            ) as mock_launch_task,
            patch(
                "app.api.routers.agent_runtime.SessionRunner.resume",
                new=AsyncMock(return_value=None),
            ) as mock_parent_resume,
            patch(
                "app.api.routers.agent_runtime.ensure_child_processing",
                new=AsyncMock(return_value=True),
            ) as mock_ensure_child_processing,
        ):
            response = await client.post(
                f"/api/v1/agent/sessions/{session_id}/tool-approval",
                json={"approval_id": "approval-child-sync-api", "approved": True},
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True
        mock_ensure_child_processing.assert_awaited_once()
        assert mock_ensure_child_processing.await_args is not None
        ensure_kwargs = mock_ensure_child_processing.await_args.kwargs
        assert ensure_kwargs["parent_session_id"] == session_id
        assert ensure_kwargs["child_run_id"] == row.id
        assert ensure_kwargs["resume_payload"] == {
            "action_type": "tool_approval",
            "approval_id": "approval-child-sync-api",
            "approved": True,
        }
        assert type(ensure_kwargs["runner"]).__name__ == "SubagentRunner"
        mock_launch_task.assert_not_awaited()
        mock_parent_resume.assert_not_awaited()

    async def test_submit_tool_approval_keeps_active_parent_revision_on_child_launch_failure(
        self,
        client: AsyncClient,
        session,
    ) -> None:
        target = await _seed_agent_target(client)
        session_response = await client.post(
            "/api/v1/agent/sessions",
            json={"project_id": target["project_id"], "model_id": target["model_id"]},
        )
        payload = session_response.json()
        session_id = payload["session_id"]
        task_id = payload["task_id"]
        row = await create_child_run(
            session,
            parent_session_id=session_id,
            parent_task_id=task_id,
            parent_thread_id=session_id,
            child_thread_id=f"{session_id}:child:launch-failure",
            agent_key="writer",
            dispatch_id="dispatch-child-launch-failure",
            tool_call_id="tool-call-child-launch-failure",
            request={"task": "write", "input": {}, "metadata": {}},
            status="waiting_user",
        )
        await record_child_run_pending_approval(
            session,
            row.id,
            approval_id="approval-child-launch-failure",
            approval_request={
                "type": "tool_approval",
                "approval_id": "approval-child-launch-failure",
                "child_run_id": row.id,
            },
        )
        task = await task_service.get_task(session, task_id)
        revision = Revision(
            project_id=task.project_id,
            task_id=task.id,
            message="active parent revision",
            agent_session_id=session_id,
            revision_type="agent",
            status="active",
            is_checkpoint=True,
            project_snapshot_title="Active parent revision",
            project_snapshot_word_count=0,
            project_snapshot_chapter_count=0,
        )
        session.add(revision)
        await session.flush()
        task.current_revision_id = revision.id
        session.add(task)
        await session.commit()

        async def fail_child_processing(**kwargs: Any) -> bool:
            raise RuntimeError("child launch failed")

        with patch(
            "app.api.routers.agent_runtime.ensure_child_processing",
            new=fail_child_processing,
        ):
            with pytest.raises(RuntimeError, match="child launch failed"):
                await client.post(
                    f"/api/v1/agent/sessions/{session_id}/tool-approval",
                    json={"approval_id": "approval-child-launch-failure", "approved": True},
                )

        await session.refresh(revision)
        assert revision.status == "active"
        await session.refresh(task)
        assert task.is_running is False

    async def test_cancel_blocks_child_approval_before_it_marks_task_running(
        self,
        client: AsyncClient,
        session,
    ) -> None:
        target = await _seed_agent_target(client)
        session_response = await client.post(
            "/api/v1/agent/sessions",
            json={"project_id": target["project_id"], "model_id": target["model_id"]},
        )
        payload = session_response.json()
        session_id = payload["session_id"]
        task_id = payload["task_id"]
        row = await create_child_run(
            session,
            parent_session_id=session_id,
            parent_task_id=task_id,
            parent_thread_id=session_id,
            child_thread_id=f"{session_id}:child:cancel-race",
            agent_key="writer",
            dispatch_id="dispatch-child-cancel-race",
            tool_call_id="tool-call-child-cancel-race",
            request={"task": "write", "input": {}, "metadata": {}},
            status="waiting_user",
        )
        await record_child_run_pending_approval(
            session,
            row.id,
            approval_id="approval-child-cancel-race",
            approval_request={
                "type": "tool_approval",
                "approval_id": "approval-child-cancel-race",
                "child_run_id": row.id,
            },
        )
        task = await task_service.get_task(session, task_id)
        revision = Revision(
            project_id=task.project_id,
            task_id=task.id,
            message="active parent revision",
            agent_session_id=session_id,
            revision_type="agent",
            status="active",
            is_checkpoint=True,
            project_snapshot_title="Active parent revision",
            project_snapshot_word_count=0,
            project_snapshot_chapter_count=0,
        )
        session.add(revision)
        await session.flush()
        task.current_revision_id = revision.id
        session.add(task)
        await session.commit()

        finalize_entered = asyncio.Event()
        release_finalize = asyncio.Event()

        async def block_finalize(
            finalize_session,
            revision_id: str,
            revision_status: str,
        ) -> None:
            assert revision_id == revision.id
            assert revision_status == "cancelled"
            finalize_entered.set()
            await release_finalize.wait()
            revision.status = revision_status
            finalize_session.add(revision)

        with (
            patch(
                "app.api.routers.agent_runtime.finalize_revision_status",
                new=block_finalize,
            ),
            patch(
                "app.api.routers.agent_runtime.ensure_child_processing",
                new=AsyncMock(return_value=True),
            ) as mock_ensure_child_processing,
            patch(
                "app.api.routers.agent_runtime.emit",
                new=AsyncMock(),
            ),
        ):
            cancel_task = asyncio.create_task(
                client.post(f"/api/v1/agent/sessions/{session_id}/cancel")
            )
            await finalize_entered.wait()
            approval_task = asyncio.create_task(
                client.post(
                    f"/api/v1/agent/sessions/{session_id}/tool-approval",
                    json={"approval_id": "approval-child-cancel-race", "approved": True},
                )
            )
            await asyncio.sleep(0.05)
            assert not approval_task.done()
            mock_ensure_child_processing.assert_not_awaited()

            release_finalize.set()
            cancel_response = await cancel_task
            approval_response = await approval_task

        assert cancel_response.status_code == status.HTTP_200_OK
        assert approval_response.status_code == status.HTTP_409_CONFLICT
        assert approval_response.json()["detail"]["code"] == "session_cancelled"
        mock_ensure_child_processing.assert_not_awaited()
        await session.refresh(task)
        await session.refresh(revision)
        assert task.is_running is False
        assert revision.status == "cancelled"

    async def test_submit_tool_approval_for_sync_child_does_not_cancel_parent_wait_task(
        self,
        client: AsyncClient,
        session,
    ) -> None:
        from app.agent_runtime.runner.run_registry import get_agent_run_registry

        target = await _seed_agent_target(client)
        session_response = await client.post(
            "/api/v1/agent/sessions",
            json={
                "project_id": target["project_id"],
                "model_id": target["model_id"],
                "max_iterations": 5,
            },
        )
        payload = session_response.json()
        session_id = payload["session_id"]
        task_id = payload["task_id"]
        row = await create_child_run(
            session,
            parent_session_id=session_id,
            parent_task_id=task_id,
            parent_thread_id=session_id,
            child_thread_id=f"{session_id}:child:sync-approval-parent-wait",
            agent_key="composer",
            dispatch_id="dispatch-child-sync-parent-wait",
            tool_call_id="tool-call-child-sync-parent-wait",
            request={"task": "make a plan", "input": {}, "metadata": {}},
            status="waiting_user",
        )
        await record_child_run_pending_approval(
            session,
            row.id,
            approval_id="approval-child-sync-parent-wait",
            approval_request={
                "type": "tool_approval",
                "approval_id": "approval-child-sync-parent-wait",
                "child_run_id": row.id,
            },
        )

        registry = get_agent_run_registry()
        gate = asyncio.Event()

        async def _wait_for_parent_gate() -> None:
            await gate.wait()

        parent_wait_task = asyncio.create_task(_wait_for_parent_gate())
        await registry.register(session_id, parent_wait_task)
        try:
            with patch(
                "app.api.routers.agent_runtime.ensure_child_processing",
                new=AsyncMock(return_value=True),
            ):
                response = await client.post(
                    f"/api/v1/agent/sessions/{session_id}/tool-approval",
                    json={
                        "approval_id": "approval-child-sync-parent-wait",
                        "approved": True,
                    },
                )

            assert response.status_code == status.HTTP_200_OK
            assert response.json()["success"] is True
            await asyncio.sleep(0.05)
            assert not parent_wait_task.cancelled()
            assert await registry.is_parent_running(session_id) is True
        finally:
            gate.set()
            await asyncio.gather(parent_wait_task, return_exceptions=True)
            await registry.unregister(session_id, parent_wait_task)
