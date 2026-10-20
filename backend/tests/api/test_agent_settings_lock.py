from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.agent_runtime import _SESSION_RUNNERS
from app.storage.models.revision import Revision
from app.storage.models.task import Task


async def _create_agent_task(
    client: AsyncClient,
    session: AsyncSession,
    *,
    is_running: bool = False,
) -> Task:
    project_response = await client.post("/api/v1/projects", data={"title": "锁定设置测试"})
    assert project_response.status_code == 201

    task = Task(
        project_id=project_response.json()["id"],
        title="Agent settings lock",
        mode="agent",
        agent_session_id="agent-settings-lock-test",
        is_running=is_running,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


@pytest.mark.asyncio
async def test_cancelling_waiting_agent_session_releases_settings_lock(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    task = await _create_agent_task(client, session)
    revision = Revision(
        project_id=task.project_id,
        task_id=task.id,
        message="等待用户回答",
        agent_session_id=task.agent_session_id,
        revision_type="agent",
        status="interrupted",
        is_checkpoint=True,
        project_snapshot_title="锁定设置测试",
        project_snapshot_word_count=0,
        project_snapshot_chapter_count=0,
    )
    session.add(revision)
    await session.flush()
    task.current_revision_id = revision.id
    session.add(task)
    await session.commit()

    runner = MagicMock(project_id=task.project_id, model_config={})
    _SESSION_RUNNERS[task.agent_session_id or ""] = runner
    try:
        with patch("app.api.routers.agent_runtime.emit", new=AsyncMock()) as emit_mock:
            cancel_response = await client.post(
                f"/api/v1/agent/sessions/{task.agent_session_id}/cancel",
            )
        lock_response = await client.get("/api/v1/settings/agent-session-lock")
    finally:
        _SESSION_RUNNERS.pop(task.agent_session_id or "", None)

    assert cancel_response.status_code == 200
    runner.cancel.assert_called_once_with()
    emitted_payloads = [call.args for call in emit_mock.await_args_list]
    assert any(
        event_name == "background:event"
        and payload.get("type") == "task_run_status_updated"
        and payload.get("task_id") == task.id
        and payload.get("is_running") is False
        for event_name, payload, *_ in emitted_payloads
    )
    assert any(
        event_name == "agent:settings_lock_changed"
        and payload == {"session_id": task.agent_session_id, "is_running": False}
        for event_name, payload, *_ in emitted_payloads
    )
    assert lock_response.json() == {"is_locked": False}
    await session.refresh(task)
    await session.refresh(revision)
    assert task.is_running is False
    assert revision.status == "cancelled"
