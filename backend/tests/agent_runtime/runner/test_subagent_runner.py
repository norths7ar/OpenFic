from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage, AIMessageChunk
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.agent_runtime.persistence import repo
from app.agent_runtime.persistence.child_runs import (
    create_child_run,
)
from app.agent_runtime.persistence.model import (
    AgentChildRun,
    AgentChildRunRequest,
)
from app.storage.models.chapter import Chapter
from app.storage.models.project import Project
from app.storage.models.project_folder import ProjectFolder as Volume
from app.storage.models.task import Task


@pytest_asyncio.fixture
async def db_session_factory() -> AsyncGenerator:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    factory = sessionmaker(  # type: ignore[call-overload]
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with factory() as session:
        session.add(Project(id="project-1", title="Project"))
        session.add(
            Volume(
                scope="writing",
                id="volume-1",
                project_id="project-1",
                title="Volume",
                order=1,
                item_count=1,
            )
        )
        session.add(
            Chapter(
                id="chapter-1",
                project_id="project-1",
                volume_id="volume-1",
                title="Chapter",
                order=1,
            )
        )
        session.add(
            Task(
                id="task-1",
                project_id="project-1",
                title="Task",
                mode="agent",
                agent_session_id="parent-session",
            )
        )
        await session.commit()
    yield factory
    await engine.dispose()


@pytest.fixture(autouse=True)
def stub_checkpointer(monkeypatch):
    monkeypatch.setattr(
        "app.agent_runtime.runner.subagent_runner.get_checkpointer",
        AsyncMock(return_value=object()),
    )


@pytest.mark.asyncio
async def test_subagent_runner_records_pending_approval_and_resume_completes_same_request(
    db_session_factory,
    monkeypatch,
):
    from app.agent_runtime.runner.subagent_runner import SubagentRunner

    async with db_session_factory() as session:
        row = await create_child_run(
            session,
            parent_session_id="parent-session",
            parent_task_id="task-1",
            parent_thread_id="parent-session",
            child_thread_id="child-thread-approval",
            agent_key="writer",
            dispatch_id="dispatch-approval",
            tool_call_id="tool-call-approval",
            request={"task": "write", "input": {}},
        )
        await repo.insert_message(
            session,
            session_id="parent-session",
            task_id="task-1",
            project_id="project-1",
            role="tool",
            status="complete",
            content='{"assistant_content": "Writer draft ready."}',
            tool_call_id="tool-call-approval",
            tool_name="dispatch_subagent",
        )

    call_count = {"count": 0}
    emitted: list[tuple[str, dict[str, object], str | None]] = []

    async def fake_emit(name, payload, room=None):
        emitted.append((name, payload, room))

    class FakeGraph:
        async def astream_events(self, initial_state, config=None, version=None):
            call_count["count"] += 1
            if call_count["count"] == 1:
                yield {
                    "event": "on_chain_end",
                    "data": {
                        "output": {
                            "messages": [],
                            "iteration_count": 1,
                            "is_done": False,
                            "final_output": None,
                            "__interrupt__": [
                                type(
                                    "Interrupt",
                                    (),
                                    {
                                        "id": "approval-1",
                                        "value": {
                                            "type": "tool_approval",
                                            "approval_id": "approval-1",
                                            "tool_name": "write_chapter",
                                        },
                                    },
                                )()
                            ],
                        }
                    },
                }
                return
            yield {
                "event": "on_chain_end",
                "data": {
                    "output": {
                        "messages": [AIMessage(content="Approved draft complete.")],
                        "iteration_count": 1,
                        "is_done": True,
                        "final_output": None,
                    }
                },
            }

        async def ainvoke(self, initial_state, config=None):
            call_count["count"] += 1
            if call_count["count"] == 1:
                return {
                    "messages": [],
                    "iteration_count": 1,
                    "is_done": False,
                    "final_output": None,
                    "__interrupt__": [
                        type(
                            "Interrupt",
                            (),
                            {
                                "id": "approval-1",
                                "value": {
                                    "type": "tool_approval",
                                    "approval_id": "approval-1",
                                    "tool_name": "write_chapter",
                                },
                            },
                        )()
                    ],
                }
            return {
                "messages": [AIMessage(content="Approved draft complete.")],
                "iteration_count": 1,
                "is_done": True,
                "final_output": None,
            }

    monkeypatch.setattr("app.agent_runtime.runner.subagent_runner.emit", fake_emit)
    monkeypatch.setattr(
        "app.agent_runtime.runner.subagent_runner.create_chat_model",
        lambda _config: object(),
    )
    monkeypatch.setattr(
        "app.agent_runtime.runner.subagent_runner.create_react_agent",
        lambda *_args, **_kwargs: FakeGraph(),
    )
    monkeypatch.setattr(
        "app.agent_runtime.runner.subagent_runner.get_checkpointer",
        AsyncMock(return_value=object()),
    )

    runner = SubagentRunner(
        session_factory=db_session_factory,
        model_config={
            "provider_type": "openai",
            "base_url": "",
            "api_key": "key",
            "model_id": "gpt-test",
            "max_context_tokens": 8000,
        },
        project_id="project-1",
    )
    interrupted = await runner.run(row.id)
    resumed = await runner.resume(
        row.id,
        {
            "action_type": "tool_approval",
            "approval_id": "approval-1",
            "approved": True,
        },
    )

    assert interrupted["approval_request"]["approval_id"] == "approval-1"
    assert resumed["assistant_content"] == "Approved draft complete."

    parent_status_payloads = [
        payload
        for name, payload, room in emitted
        if name == "agent:subagent_status" and room == "agent_subagents:parent-session"
    ]
    assert any(
        payload.get("status") == "waiting_user"
        and payload.get("pending_approval", {}).get("approval_id") == "approval-1"
        for payload in parent_status_payloads
    )
    assert any(
        payload.get("status") == "running" and payload.get("pending_approval") is None
        for payload in parent_status_payloads
    )

    async with db_session_factory() as session:
        updated = await session.get(AgentChildRun, row.id)
        requests = (
            (
                await session.execute(
                    select(AgentChildRunRequest)
                    .where(AgentChildRunRequest.child_run_id == row.id)
                    .order_by(AgentChildRunRequest.seq.asc())
                )
            )
            .scalars()
            .all()
        )

    assert updated is not None
    assert updated.pending_approval_id is None
    assert updated.status == "completed"
    assert requests[0].status == "completed"
    assert requests[0].assistant_content == "Approved draft complete."


@pytest.mark.asyncio
async def test_subagent_runner_streams_and_persists_child_transcript_on_child_thread(
    db_session_factory,
    monkeypatch,
):
    from app.agent_runtime.runner.subagent_runner import SubagentRunner

    async with db_session_factory() as session:
        row = await create_child_run(
            session,
            parent_session_id="parent-session",
            parent_task_id="task-1",
            parent_thread_id="parent-session",
            child_thread_id="child-thread-transcript",
            agent_key="writer",
            dispatch_id="dispatch-transcript",
            tool_call_id="tool-call-transcript",
            request={"task": "write child transcript", "input": {}},
        )

    emitted: list[tuple[str, dict, str | None]] = []

    async def fake_emit(name, payload, room=None):
        emitted.append((name, payload, room))

    class FakeGraph:
        async def astream_events(self, initial_state, config=None, version=None):
            assert version == "v2"
            assert config is not None
            assert config["configurable"]["thread_id"] == "child-thread-transcript"
            assert "subagent_child" in config["tags"]
            yield {
                "event": "on_chain_start",
                "name": "writer",
                "tags": ["agent_node", "subagent_child"],
                "data": {},
            }
            yield {
                "event": "on_chat_model_start",
                "run_id": "child-run-1",
                "tags": ["subagent_child"],
                "data": {},
            }
            yield {
                "event": "on_chat_model_stream",
                "run_id": "child-run-1",
                "tags": ["subagent_child"],
                "data": {"chunk": AIMessageChunk(content="child stream output")},
            }
            yield {
                "event": "on_chat_model_end",
                "run_id": "child-run-1",
                "tags": ["subagent_child"],
                "data": {"output": AIMessageChunk(content="child stream output")},
            }
            yield {
                "event": "on_tool_start",
                "name": "read_chapter",
                "run_id": "child-tool-1",
                "tags": ["subagent_child"],
                "data": {"input": {"order": 1}},
                "metadata": {"tool_call_id": "call-child-tool"},
            }
            yield {
                "event": "on_tool_end",
                "name": "read_chapter",
                "run_id": "child-tool-1",
                "tags": ["subagent_child"],
                "metadata": {"tool_call_id": "call-child-tool"},
                "data": {
                    "input": {"order": 1},
                    "output": "child tool output",
                },
            }
            yield {
                "event": "on_chain_end",
                "tags": ["subagent_child"],
                "data": {
                    "output": {
                        "messages": [AIMessage(content="child stream output")],
                        "iteration_count": 1,
                        "is_done": True,
                        "final_output": None,
                    }
                },
            }

        async def ainvoke(self, initial_state, config=None):
            return {
                "messages": [AIMessage(content="child stream output")],
                "iteration_count": 1,
                "is_done": True,
                "final_output": None,
            }

    monkeypatch.setattr("app.agent_runtime.runner.subagent_runner.emit", fake_emit)
    monkeypatch.setattr(
        "app.agent_runtime.runner.subagent_runner.create_chat_model",
        lambda _config: object(),
    )
    monkeypatch.setattr(
        "app.agent_runtime.runner.subagent_runner.create_react_agent",
        lambda *_args, **_kwargs: FakeGraph(),
    )

    runner = SubagentRunner(
        session_factory=db_session_factory,
        model_config={
            "provider_type": "openai",
            "base_url": "",
            "api_key": "key",
            "model_id": "gpt-test",
            "max_context_tokens": 8000,
        },
        project_id="project-1",
    )
    result = await runner.run(row.id)

    assert result["assistant_content"] == "child stream output"

    child_events = [
        (name, payload, room)
        for name, payload, room in emitted
        if payload.get("session_id") == "child-thread-transcript"
    ]
    assert child_events == [
        (
            "agent:token",
            {
                "session_id": "child-thread-transcript",
                "run_id": "child-run-1",
                "content": "child stream output",
            },
            "agent_subagent_session:child-thread-transcript",
        ),
        (
            "agent:tool_call",
            {
                "session_id": "child-thread-transcript",
                "run_id": "child-tool-1",
                "tool_call_id": "call-child-tool",
                "tool": "read_chapter",
                "input": {"order": 1},
            },
            "agent_subagent_session:child-thread-transcript",
        ),
        (
            "agent:tool_result",
            {
                "session_id": "child-thread-transcript",
                "run_id": "child-tool-1",
                "tool_call_id": "call-child-tool",
                "tool": "read_chapter",
                "input": {"order": 1},
                "output": "child tool output",
            },
            "agent_subagent_session:child-thread-transcript",
        ),
        (
            "agent:done",
            {
                "session_id": "child-thread-transcript",
                "created_at": child_events[-1][1]["created_at"],
            },
            "agent_subagent_session:child-thread-transcript",
        ),
    ]
    assert all(
        not (
            room == "agent_session:parent-session"
            and payload.get("session_id") == "child-thread-transcript"
        )
        for _, payload, room in emitted
    )

    async with db_session_factory() as session:
        child_messages = await repo.list_by_session(session, "child-thread-transcript")
        parent_messages = await repo.list_by_session(session, "parent-session")

    assert [message.role for message in child_messages] == ["assistant", "tool"]
    assert child_messages[0].content == "child stream output"
    assert child_messages[0].agent_id == "writer"
    assert child_messages[1].content == "child tool output"
    assert child_messages[1].tool_call_id == "call-child-tool"
    assert all(message.session_id != "child-thread-transcript" for message in parent_messages)
