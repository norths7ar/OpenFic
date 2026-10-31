"""Project deletion lifecycle, including its intentional cross-store commit boundary."""

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.agent_runtime.attachments import delete_attachments_for_task
from app.agent_runtime.persistence.model import AgentChildRun
from app.agent_runtime.runner.checkpointer import delete_checkpoints_for_thread
from app.storage.models.task import Task
from app.storage.services import project_service, task_service


class ProjectHasRunningTasksError(Exception):
    pass


async def _list_project_checkpoint_thread_ids(
    session: AsyncSession,
    project_id: str,
) -> list[str]:
    task_result = await session.execute(
        select(col(Task.agent_session_id)).where(col(Task.project_id) == project_id)
    )
    child_result = await session.execute(
        select(col(AgentChildRun.child_thread_id)).where(
            col(AgentChildRun.parent_task_id).in_(
                select(col(Task.id)).where(col(Task.project_id) == project_id)
            )
        )
    )
    return [
        *(session_id for session_id in task_result.scalars().all() if session_id),
        *(thread_id for thread_id in child_result.scalars().all() if thread_id),
    ]


async def delete_project(session: AsyncSession, project_id: str) -> None:
    logger.info(f"删除项目: {project_id}")
    tasks = (await task_service.list_tasks(session, project_id)).items
    if any(task.is_running for task in tasks):
        raise ProjectHasRunningTasksError("项目存在运行中任务，不能删除")
    checkpoint_thread_ids = await _list_project_checkpoint_thread_ids(session, project_id)
    for task in tasks:
        await delete_attachments_for_task(session, task_id=task.id)
    await project_service.delete_project(session, project_id)
    await session.commit()
    for thread_id in checkpoint_thread_ids:
        deleted_rows = await delete_checkpoints_for_thread(thread_id)
        logger.bind(project_id=project_id, thread_id=thread_id).info(
            "Deleted {} checkpoint rows for project cleanup",
            deleted_rows,
        )
