"""Task API projection for agent runtime messages."""

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.persistence import repo
from app.agent_runtime.persistence.child_runs import create_child_run
from app.agent_runtime.persistence.task_projection import (
    load_task_messages_for_agent_session,
)


@pytest.mark.asyncio
async def test_projects_compaction_marker_as_display_only_task_message(
    db_session: AsyncSession,
    sample_task,
) -> None:
    sid = "session_projection_compaction"

    await repo.insert_message(
        db_session,
        session_id=sid,
        task_id=sample_task.id,
        project_id=sample_task.project_id,
        role="user",
        content="原始请求",
        status="sent",
    )
    await repo.insert_message(
        db_session,
        session_id=sid,
        task_id=sample_task.id,
        project_id=sample_task.project_id,
        role="system",
        content="已进行压缩",
        status="complete",
        message_type="compaction",
        display_channel="list",
        llm_visibility="hidden",
        metadata={
            "kind": "compaction",
            "compaction_id": "cmp_projection",
            "trigger": "manual",
            "start_seq": 1,
            "end_seq": 4,
            "source_input_tokens": 100,
            "summary_tokens": 10,
        },
        message_id="compaction:cmp_projection",
    )

    messages = await load_task_messages_for_agent_session(db_session, sid)

    assert [message.message_type for message in messages] == [
        "user_request",
        "compaction",
    ]
    compaction_message = messages[1]
    assert compaction_message.id == "compaction:cmp_projection"
    assert compaction_message.role == "system"
    assert compaction_message.content == "已进行压缩"
    assert compaction_message.display_channel == "list"
    assert compaction_message.message_status == "completed"
    assert compaction_message.payload == {"kind": "compaction"}
    assert compaction_message.correlation_id == "compaction:cmp_projection"


@pytest.mark.asyncio
async def test_projection_filters_subagent_internal_rows_from_parent_session(
    db_session: AsyncSession,
    sample_task,
) -> None:
    sid = "session_projection_subagent_leak"

    await repo.insert_message(
        db_session,
        session_id=sid,
        task_id=sample_task.id,
        project_id=sample_task.project_id,
        role="assistant",
        agent_id="primary",
        content="",
        status="complete",
        tool_calls=[
            {
                "id": "dispatch-call",
                "name": "dispatch_subagent",
                "args": {"agent_key": "writer", "task": "write"},
            }
        ],
    )
    await repo.insert_message(
        db_session,
        session_id=sid,
        task_id=sample_task.id,
        project_id=sample_task.project_id,
        role="tool",
        content='{"success": true, "status": "completed", "child_run_id": "child-1"}',
        status="complete",
        tool_call_id="dispatch-call",
        tool_name="dispatch_subagent",
    )
    await repo.insert_message(
        db_session,
        session_id=sid,
        task_id=sample_task.id,
        project_id=sample_task.project_id,
        role="assistant",
        agent_id="writer",
        content="child draft internals",
        status="complete",
        tool_calls=[
            {
                "id": "child-write-call",
                "name": "write_chapter",
                "args": {"title": "chapter draft"},
            }
        ],
    )
    await repo.insert_message(
        db_session,
        session_id=sid,
        task_id=sample_task.id,
        project_id=sample_task.project_id,
        role="tool",
        content='{"success": true, "title": "chapter draft"}',
        status="complete",
        tool_call_id="child-write-call",
        tool_name="write_chapter",
    )
    await repo.insert_message(
        db_session,
        session_id=sid,
        task_id=sample_task.id,
        project_id=sample_task.project_id,
        role="system",
        status="complete",
        agent_id="writer",
        message_type="node_start",
        display_channel="hidden",
        metadata={
            "kind": "agent_node",
            "event_type": "node_start",
            "node": "writer",
            "phase": "start",
            "node_status": "running",
        },
    )

    messages = await load_task_messages_for_agent_session(db_session, sid)

    assert [message.tool_call_id for message in messages] == [
        None,
        "dispatch-call",
    ]
    assert messages[0].tool_calls == [
        {
            "id": "dispatch-call",
            "name": "dispatch_subagent",
            "args": {"agent_key": "writer", "task": "write"},
        }
    ]
    assert messages[1].message_type == "tool"
    assert messages[1].payload["tool_name"] == "dispatch_subagent"


@pytest.mark.asyncio
async def test_projects_subagent_identity_for_orchestration_tool_results(
    db_session: AsyncSession,
    sample_task,
) -> None:
    session_id = "session_projection_subagent_identity"
    dispatch_id = "dispatch-writer"
    await repo.insert_message(
        db_session,
        session_id=session_id,
        task_id=sample_task.id,
        project_id=sample_task.project_id,
        role="assistant",
        agent_id="primary",
        content="",
        status="complete",
        tool_calls=[
            {
                "id": "call-dispatch",
                "name": "dispatch_subagent",
                "args": {
                    "agent_type": "writer",
                    "description": "续写场景",
                    "prompt": "请续写这一场景。",
                },
            },
            {
                "id": "call-notify",
                "name": "notify_subagent",
                "args": {
                    "dispatch_id": dispatch_id,
                    "prompt": "继续完善冲突。",
                },
            },
            {
                "id": "call-recycle",
                "name": "recycle_subagent",
                "args": {
                    "dispatch_id": dispatch_id,
                    "reason": "任务完成",
                },
            },
        ],
    )
    await create_child_run(
        db_session,
        parent_session_id=session_id,
        parent_task_id=sample_task.id,
        parent_thread_id=session_id,
        child_thread_id=f"{session_id}:child:{dispatch_id}",
        agent_key="writer",
        dispatch_id=dispatch_id,
        tool_call_id="call-dispatch",
        request={"task": "请续写这一场景。"},
        metadata={"agent_number": "#1001"},
    )
    for tool_call_id, tool_name, result in [
        (
            "call-dispatch",
            "dispatch_subagent",
            {"dispatch_id": dispatch_id, "agent_number": "#1001", "result": "完成"},
        ),
        (
            "call-notify",
            "notify_subagent",
            {"dispatch_id": dispatch_id, "agent_number": "#1001", "result": "已继续"},
        ),
        (
            "call-recycle",
            "recycle_subagent",
            {"dispatch_id": dispatch_id, "recycled": True},
        ),
    ]:
        await repo.insert_message(
            db_session,
            session_id=session_id,
            task_id=sample_task.id,
            project_id=sample_task.project_id,
            role="tool",
            content=json.dumps(result, ensure_ascii=False),
            status="complete",
            tool_call_id=tool_call_id,
            tool_name=tool_name,
        )

    messages = await load_task_messages_for_agent_session(db_session, session_id)

    tool_messages = [message for message in messages if message.message_type == "tool"]
    assert len(tool_messages) == 3
    assert [message.payload["tool_args"] for message in tool_messages] == [
        {
            "agent_type": "writer",
            "description": "续写场景",
            "prompt": "请续写这一场景。",
        },
        {"dispatch_id": dispatch_id, "prompt": "继续完善冲突。"},
        {"dispatch_id": dispatch_id, "reason": "任务完成"},
    ]
    assert [message.payload["tool_result"]["agent_key"] for message in tool_messages] == [
        "writer",
        "writer",
        "writer",
    ]
    assert [message.payload["tool_result"]["agent_number"] for message in tool_messages] == [
        "#1001",
        "#1001",
        "#1001",
    ]
