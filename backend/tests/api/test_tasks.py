"""Task API contract tests for agent-runtime backed tasks."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.modes import AgentMode
from app.storage.models.revision import Revision
from app.storage.services import task_service


@pytest.mark.asyncio
class TestTaskAPI:
    async def create_project_and_chapter(self, client: AsyncClient) -> tuple[str, str]:
        project_response = await client.post("/api/v1/projects", data={"title": "测试项目"})
        assert project_response.status_code == status.HTTP_201_CREATED
        project_id = project_response.json()["id"]
        volumes_response = await client.get(f"/api/v1/projects/{project_id}/volumes")
        assert volumes_response.status_code == status.HTTP_200_OK
        volume_id = volumes_response.json()[0]["id"]

        chapter_response = await client.post(
            f"/api/v1/projects/{project_id}/chapters",
            json={
                "volume_id": volume_id,
                "title": "测试章节",
                "content": "测试内容",
            },
        )
        assert chapter_response.status_code == status.HTTP_201_CREATED
        chapter_id = chapter_response.json()["id"]
        return project_id, chapter_id

    async def create_agent_task(
        self,
        client: AsyncClient,
        session: AsyncSession,
        *,
        title: str = "Agent 任务",
        session_id: str | None = "session-task-api",
        mode: AgentMode = "agent",
    ):
        project_id, chapter_id = await self.create_project_and_chapter(client)
        task = await task_service.create_task(
            session,
            project_id=project_id,
            title=title,
            mode=mode,
            agent_session_id=session_id,
        )
        await session.commit()
        return task, project_id, chapter_id


    async def test_list_tasks_ignores_pending_interrupt_for_cancelled_revision(
        self,
        client: AsyncClient,
        session: AsyncSession,
    ) -> None:
        task, project_id, _chapter_id = await self.create_agent_task(
            client,
            session,
            title="宸插彇娑堢殑浠诲姟",
        )
        revision = Revision(
            project_id=task.project_id,
            task_id=task.id,
            message="cancelled approval",
            agent_session_id=task.agent_session_id,
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
        task.is_running = False
        session.add(task)
        await session.commit()

        fake_checkpointer = AsyncMock()
        fake_checkpointer.aget_tuple.return_value = SimpleNamespace(
            pending_writes=[
                (
                    "task-write",
                    "__interrupt__",
                    [SimpleNamespace(value={"type": "tool_approval"})],
                )
            ]
        )
        with patch(
            "app.api.routers.tasks.get_checkpointer",
            new=AsyncMock(return_value=fake_checkpointer),
        ):
            response = await client.get(f"/api/v1/projects/{project_id}/tasks")

        assert response.status_code == status.HTTP_200_OK
        items = {item["id"]: item for item in response.json()["items"]}
        assert items[task.id]["is_running"] is False
