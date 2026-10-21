import asyncio
from collections import deque
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.background.events.publisher import BackgroundEventPublisher
from app.background.jobs import repos as job_repo
from app.background.jobs import service as background_service
from app.background.jobs.base import JobDefinition
from app.background.jobs.constants import (
    JOB_TYPE_SUMMARY_BATCH,
)
from app.background.jobs.definitions import register_all_background_jobs
from app.background.jobs.definitions import summary_batch as summary_batch_definition
from app.background.jobs.models import BackgroundJob, BackgroundJobItem
from app.background.jobs.states import (
    JOB_STATUS_CANCELLED,
    JOB_STATUS_FAILED,
)
from app.background.runtime.context import JobContext
from app.background.runtime.registry import get_job_registry
from app.background.runtime.worker import BackgroundWorker
from app.background.transport.base import BackgroundTransport
from app.background.transport.messages import BackgroundEventMessage, JobNotification
from app.storage import database
from app.storage.models.chapter import Chapter
from app.storage.models.chapter_summary import ChapterSummary
from app.storage.models.project import Project
from app.storage.models.project_folder import ProjectFolder as Volume
from app.storage.repos.chapter_summary_repo import (
    SUMMARY_STATUS_FAILED,
    SUMMARY_STATUS_QUEUED,
)
from tests.model_registry import register_sqlmodel_models


def _default_volume_id(project: Project) -> str:
    return f"{project.id}-volume-1"


def _default_volume(project: Project, *, chapter_count: int = 1) -> Volume:
    return Volume(
        scope="writing",
        id=_default_volume_id(project),
        project_id=project.id,
        title="第一卷",
        order=1,
        item_count=chapter_count,
    )


async def _configure_file_database(tmp_path=None):
    register_sqlmodel_models()

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    database._async_session_factory = factory
    return engine, factory


class _NoopInput(BaseModel):
    value: str


async def _failing_handler(context: JobContext) -> None:
    raise RuntimeError("handler failed")


async def _failing_failure_hook(_context: JobContext, _reason: str) -> None:
    raise RuntimeError("failure hook failed")


async def _cancelled_hook(context: JobContext, reason: str) -> None:
    await background_service.append_event(
        context.session,
        context.publisher,
        context.job,
        event_type="cancelled_hook_ran",
        payload={"reason": reason},
    )


class RecordingTransport(BackgroundTransport):
    def __init__(self) -> None:
        self.job_notifications: deque[JobNotification] = deque()
        self.events: deque[BackgroundEventMessage] = deque()

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def notify_job(self, message: JobNotification) -> None:
        self.job_notifications.append(message)

    async def receive_job(self, timeout_ms: int) -> JobNotification | None:
        if not self.job_notifications:
            return None
        return self.job_notifications.popleft()

    async def publish_event(self, message: BackgroundEventMessage) -> None:
        self.events.append(message)

    async def receive_event(self, timeout_ms: int) -> BackgroundEventMessage | None:
        if not self.events:
            return None
        return self.events.popleft()


@pytest.fixture(autouse=True)
def reset_background_registry():
    original_session_factory = database._async_session_factory
    registry = get_job_registry()
    registry.clear()
    register_all_background_jobs()
    yield
    registry.clear()
    database._async_session_factory = original_session_factory


@pytest.mark.asyncio
async def test_worker_marks_job_failed_when_failure_hook_raises(tmp_path):
    engine, factory = await _configure_file_database(tmp_path)
    session = factory()
    try:
        get_job_registry().register(
            JobDefinition(
                type="failing_hook_job",
                name="Failing hook job",
                description="Fails while finalizing a failed job.",
                input_model=_NoopInput,
                handler=_failing_handler,
                on_failed=_failing_failure_hook,
            )
        )
        job = await job_repo.create_job(
            session,
            BackgroundJob(type="failing_hook_job", payload_json='{"value":"x"}'),
        )
        await background_service.commit_and_notify(session)

        worker = BackgroundWorker(
            worker_id="worker-1",
            transport=RecordingTransport(),
            scan_interval_seconds=1,
        )
        with patch.object(JobContext, "check_cancelled", new_callable=AsyncMock):
            await worker._run_job(job.id)

        session.expire(job)
        await session.refresh(job)
        assert job.status == JOB_STATUS_FAILED
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_interrupts_running_summary_batch_on_cancel_request(tmp_path):
    engine, factory = await _configure_file_database(tmp_path)
    session = factory()
    try:
        generation_started = asyncio.Event()
        generation_cancelled = asyncio.Event()

        async def blocking_summary_handler(_context: JobContext) -> None:
            generation_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                generation_cancelled.set()
                raise

        get_job_registry()._definitions[JOB_TYPE_SUMMARY_BATCH] = JobDefinition(
            type=JOB_TYPE_SUMMARY_BATCH,
            name="Blocking summary batch",
            description="Blocks until cancellation for worker cancellation coverage.",
            input_model=_NoopInput,
            handler=blocking_summary_handler,
            on_cancelled=_cancelled_hook,
            supports_cancel=True,
        )
        job = await job_repo.create_job(
            session,
            BackgroundJob(type=JOB_TYPE_SUMMARY_BATCH, payload_json='{"value":"x"}'),
        )
        await background_service.commit_and_notify(session)

        transport = RecordingTransport()
        worker = BackgroundWorker(
            worker_id="worker-1", transport=transport, scan_interval_seconds=1
        )
        run_task = asyncio.create_task(worker._run_job(job.id))
        await asyncio.wait_for(generation_started.wait(), timeout=1)

        cancel_session = factory()
        try:
            stored_job = await job_repo.get_job(cancel_session, job.id)
            assert stored_job is not None
            await background_service.request_cancel(
                cancel_session,
                BackgroundEventPublisher(transport),
                stored_job,
                reason="用户停止摘要生成队列",
            )
            await background_service.commit_and_notify(cancel_session)
        finally:
            await cancel_session.close()

        assert worker.cancel_running_summary_batch(job.id) is True
        await asyncio.wait_for(run_task, timeout=1)
        assert generation_cancelled.is_set()

        verification_session = factory()
        try:
            stored_job = await job_repo.get_job(verification_session, job.id)
            events = await job_repo.list_events(verification_session, job_id=job.id)
        finally:
            await verification_session.close()
        assert stored_job is not None
        assert stored_job.status == JOB_STATUS_CANCELLED
        assert any(event.event_type == "cancelled_hook_ran" for event in events)
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_summary_batch_failure_hook_marks_incomplete_items_failed(tmp_path, monkeypatch):
    engine, factory = await _configure_file_database(tmp_path)
    session = factory()
    try:
        project = Project(title="项目", description="")
        chapter = Chapter(
            project_id=project.id,
            volume_id=_default_volume_id(project),
            title="第一章",
            content="正文" * 400,
            word_count=800,
            order=1,
        )
        session.add(project)
        session.add(_default_volume(project))
        session.add(chapter)
        await session.commit()

        summary = ChapterSummary(
            project_id=project.id,
            summary_type="chapter",
            status=SUMMARY_STATUS_QUEUED,
            chapter_id=chapter.id,
            chapter_order=chapter.order,
            start_order=chapter.order,
            end_order=chapter.order,
        )
        session.add(summary)
        await session.commit()

        job = await background_service.submit_job(
            session,
            job_type="summary_batch",
            payload={"project_id": project.id},
            context={"project_id": project.id, "model_policy": "light_model"},
            subject_type="project",
            subject_id=project.id,
        )
        job_id = job.id
        item = await background_service.create_item(
            session,
            job_id=job_id,
            item_key=f"chapter:{chapter.id}",
            item_type="chapter_summary",
            payload={"project_id": project.id, "chapter_id": chapter.id},
            order_index=0,
        )
        item_id = item.id
        summary_id = summary.id
        summary.job_id = item.id
        await session.commit()

        async def fail_mark_item_running(_session, _item):
            raise RuntimeError("batch crashed before item start")

        monkeypatch.setattr(summary_batch_definition, "_mark_item_running", fail_mark_item_running)

        transport = RecordingTransport()
        worker = BackgroundWorker(
            worker_id="worker-1", transport=transport, scan_interval_seconds=1
        )
        await worker._run_job(job_id)

        verification_session = factory()
        try:
            stored_job = await job_repo.get_job(verification_session, job_id)
            stored_item = await verification_session.get(BackgroundJobItem, item_id)
            stored_summary = await verification_session.get(ChapterSummary, summary_id)
        finally:
            await verification_session.close()
        assert stored_job is not None
        assert stored_item is not None
        assert stored_summary is not None
        assert stored_job.status == JOB_STATUS_FAILED
        assert stored_item.status == JOB_STATUS_FAILED
        assert stored_summary.status == SUMMARY_STATUS_FAILED
        assert stored_summary.error_message == "batch crashed before item start"
    finally:
        await session.close()
        await engine.dispose()
