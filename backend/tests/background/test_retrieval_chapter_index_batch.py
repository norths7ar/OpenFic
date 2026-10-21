"""Retrieval chapter index background job tests."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.background.events.publisher import BackgroundEventPublisher
from app.background.jobs.definitions import retrieval_chapter_index_batch as definition
from app.background.jobs.models import BackgroundJob, BackgroundJobItem
from app.background.jobs.states import (
    JOB_STATUS_CANCELLED,
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCEEDED,
)
from app.background.runtime.context import JobCancelledError, JobContext
from app.core.encryption import EncryptionService
from app.models.repos import model_provider_repo, model_repo
from app.retrieval.chapter_index import (
    ChapterIndexIntegrationService,
    ChunkBatchIndexProgress,
)
from app.retrieval.types import ChunkIndexResult
from app.storage.models.chapter import Chapter
from app.storage.models.project import Project
from app.storage.models.project_folder import ProjectFolder as Volume
from app.storage.models.retrieval_chapter_index_state import RetrievalChapterIndexState
from app.storage.repos import setting_repo


class FakeEmbeddingConfig:
    model_id = "fake-embedding"
    dimensions = 3


class FakeEmbeddingClient:
    config = FakeEmbeddingConfig()

    async def embed(self, texts):
        return None

    async def embed_single(self, text):
        return [0.0, 0.0, 0.0]


class FakeRetrievalService:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def register_index(self, *args, **kwargs):
        return None

    async def index_chunk_batch(self, session, index_key, chunks, embedding_client, **kwargs):
        _ = (session, index_key, embedding_client, kwargs)
        if self.fail:
            raise RuntimeError("vector store failed")
        return ChunkIndexResult(succeeded_chunk_count=len(chunks))

    async def finalize_chunk_index(self, session, index_key):
        _ = (session, index_key)


class ContentChangingRetrievalService(FakeRetrievalService):
    async def index_chunk_batch(self, session, index_key, chunks, embedding_client, **kwargs):
        _ = (index_key, embedding_client, kwargs)
        from sqlalchemy import select
        from sqlmodel import col

        chapter_id = chunks[0].metadata["chapter_id"]
        chapter = (
            await session.execute(select(Chapter).where(col(Chapter.id) == chapter_id))
        ).scalar_one()
        chapter.content = "英雄在索引期间改写了正文"
        await session.flush()
        return await super().index_chunk_batch(
            session,
            index_key,
            chunks,
            embedding_client,
            **kwargs,
        )


async def _noop_check_cancelled() -> None:
    return None


async def _create_embedding_model(session: AsyncSession, model_id: str = "fake-embedding"):
    from app.settings import settings

    encryption_service = EncryptionService(settings.encryption_key)
    provider = await model_provider_repo.create(
        session=session,
        name="Provider",
        url="https://api.test.com",
        api_key_encrypted=encryption_service.encrypt("test-key"),
        provider_type="openai",
    )
    return await model_repo.create(
        session=session,
        name="Embedding",
        provider_id=provider.id,
        model_id=model_id,
        task_type="embedding",
        dimensions=3,
    )


async def _seed_job(session: AsyncSession, *, fail: bool = False):
    model = await _create_embedding_model(session)
    await setting_repo.upsert(session, "default_embedding_model", model.id)
    project = Project(id="project-1", title="项目", description="")
    volume = Volume(scope="writing", id="volume-1", project_id=project.id, title="第一卷", order=1)
    chapter = Chapter(
        id="chapter-1",
        project_id=project.id,
        volume_id=volume.id,
        title="第一章",
        content="英雄遇见龙",
        word_count=5,
        order=1,
    )
    job = BackgroundJob(
        type="retrieval_chapter_index_batch",
        status=JOB_STATUS_PENDING,
        payload_json='{"project_id":"project-1"}',
        context_json=f'{{"embedding_model_ref_id":"{model.id}"}}',
        subject_type="project",
        subject_id=project.id,
    )
    session.add(project)
    session.add(volume)
    session.add(chapter)
    session.add(job)
    await session.flush()
    item = BackgroundJobItem(
        job_id=job.id,
        item_key=f"chapter:{chapter.id}",
        type="retrieval_chapter",
        status=JOB_STATUS_PENDING,
        payload_json=f'{{"project_id":"{project.id}","chapter_id":"{chapter.id}"}}',
        order_index=0,
    )
    state = RetrievalChapterIndexState(
        project_id=project.id,
        chapter_id=chapter.id,
        index_key=f"chapters:{project.id}",
        status="queued",
        source_hash="old",
        embedding_model_ref_id=model.id,
        job_id=job.id,
        item_id=item.id,
    )
    session.add(item)
    session.add(state)
    await session.commit()
    return job, item, state, fail


@pytest.mark.asyncio
async def test_retrieval_chapter_index_batch_marks_stale_if_content_changes_during_index(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job, item, state, _ = await _seed_job(session)
    state.item_id = item.id
    await session.commit()
    monkeypatch.setattr(
        definition,
        "_build_embedding_client",
        lambda session, model_ref_id: FakeEmbeddingClient(),
    )
    monkeypatch.setattr(
        definition,
        "ChapterIndexIntegrationService",
        lambda: ChapterIndexIntegrationService(retrieval_service=ContentChangingRetrievalService()),
    )

    context = JobContext(
        session=session,
        job=job,
        publisher=BackgroundEventPublisher(),
    )
    context.check_cancelled = _noop_check_cancelled  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await definition.handle_retrieval_chapter_index_batch(context)

    await session.refresh(item)
    await session.refresh(state)
    assert item.status == JOB_STATUS_FAILED
    assert "chapter content changed during indexing" in (item.error_json or "")
    assert state.status == "stale"
    assert state.job_id is None
    assert state.item_id is None
    assert state.error_message is None


class MultiDocumentRetrievalService:
    """处理多文档的检索服务替身：所有文档都成功。"""

    async def register_index(self, *args, **kwargs):
        return None

    async def index_chunk_batch(self, session, index_key, chunks, embedding_client, **kwargs):
        _ = (session, index_key, embedding_client, kwargs)
        return ChunkIndexResult(succeeded_chunk_count=len(chunks))

    async def finalize_chunk_index(self, session, index_key):
        _ = (session, index_key)


class StopsAfterStartingFirstChapterIndexService:
    async def stream_index_chapters(
        self,
        session,
        *,
        chapter_ids,
        embedding_client,
        embedding_model,
        job_id,
        max_chunks_per_batch,
        check_cancelled=None,
        on_chapter_started=None,
    ):
        _ = (
            session,
            embedding_client,
            embedding_model,
            job_id,
            max_chunks_per_batch,
            check_cancelled,
        )
        if False:
            yield ChunkBatchIndexProgress([])
        assert on_chapter_started is not None
        await on_chapter_started(chapter_ids[0])
        raise JobCancelledError("用户停止索引")


async def _seed_multi_chapter_job(session: AsyncSession, *, chapter_count: int):
    """创建含多个章节的索引任务，返回 (job, items, states)。"""
    model = await _create_embedding_model(session)
    await setting_repo.upsert(session, "default_embedding_model", model.id)
    project = Project(id="project-multi", title="多章项目", description="")
    volume = Volume(scope="writing", id="volume-multi", project_id=project.id, title="卷", order=1)
    session.add(project)
    session.add(volume)

    job = BackgroundJob(
        type="retrieval_chapter_index_batch",
        status=JOB_STATUS_PENDING,
        payload_json='{"project_id":"project-multi"}',
        context_json=f'{{"embedding_model_ref_id":"{model.id}"}}',
        subject_type="project",
        subject_id=project.id,
    )
    session.add(job)
    await session.flush()

    items = []
    states = []
    for i in range(chapter_count):
        chapter_id = f"chapter-multi-{i}"
        chapter = Chapter(
            id=chapter_id,
            project_id=project.id,
            volume_id=volume.id,
            title=f"第{i + 1}章",
            content=f"内容{i}",
            word_count=3,
            order=i + 1,
        )
        item = BackgroundJobItem(
            job_id=job.id,
            item_key=f"chapter:{chapter_id}",
            type="retrieval_chapter",
            status=JOB_STATUS_PENDING,
            payload_json=f'{{"project_id":"{project.id}","chapter_id":"{chapter_id}"}}',
            order_index=i,
        )
        state = RetrievalChapterIndexState(
            project_id=project.id,
            chapter_id=chapter_id,
            index_key=f"chapters:{project.id}",
            status="queued",
            source_hash="old",
            embedding_model_ref_id=model.id,
            job_id=job.id,
            item_id=item.id,
        )
        session.add(chapter)
        session.add(item)
        session.add(state)
        items.append(item)
        states.append(state)

    await session.commit()
    return job, items, states


@pytest.mark.asyncio
async def test_batch_cancellation_preserves_completed_chapters_and_resets_incomplete_ones(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """取消时保留已完成章节，仅清理尚未完成章节的部分索引。"""
    monkeypatch.setattr(definition, "MAX_EMBEDDING_CHUNKS_PER_REQUEST", 1)
    job, items, states = await _seed_multi_chapter_job(session, chapter_count=2)
    monkeypatch.setattr(
        definition,
        "_build_embedding_client",
        lambda session, model_ref_id: FakeEmbeddingClient(),
    )
    monkeypatch.setattr(
        definition,
        "ChapterIndexIntegrationService",
        lambda: ChapterIndexIntegrationService(retrieval_service=MultiDocumentRetrievalService()),
    )

    deleted_document_ids: list[str] = []

    class CleanupRetrievalService:
        async def delete_documents(self, session, index_key, document_ids):
            _ = (session, index_key)
            deleted_document_ids.extend(document_ids)

    monkeypatch.setattr(definition, "OpenFicRetrievalService", CleanupRetrievalService)

    emit_count = 0

    async def count_emit(*_args, **_kwargs):
        nonlocal emit_count
        emit_count += 1

    monkeypatch.setattr(definition, "commit_and_emit_index_status", count_emit)

    check_count = 0

    async def cancel_before_second_chapter() -> None:
        nonlocal check_count
        check_count += 1
        if check_count >= 6:
            raise JobCancelledError("用户停止索引")

    context = JobContext(
        session=session,
        job=job,
        publisher=BackgroundEventPublisher(),
    )
    context.check_cancelled = cancel_before_second_chapter  # type: ignore[method-assign]

    with pytest.raises(JobCancelledError, match="用户停止索引"):
        await definition.handle_retrieval_chapter_index_batch(context)
    await definition._handle_cancelled(context, "用户停止索引")

    await session.refresh(items[0])
    await session.refresh(items[1])
    await session.refresh(states[0])
    await session.refresh(states[1])
    assert items[0].status == JOB_STATUS_SUCCEEDED
    assert states[0].status == "ready"
    assert items[1].status == JOB_STATUS_CANCELLED
    assert states[1].status == "needs_rebuild"
    assert states[1].job_id is None
    assert states[1].item_id is None
    assert states[1].error_message is None
    assert deleted_document_ids == []
    assert emit_count == 2


@pytest.mark.asyncio
async def test_batch_cancellation_batches_pending_items_and_cleans_only_running_chapter(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job, items, states = await _seed_multi_chapter_job(session, chapter_count=3)
    monkeypatch.setattr(
        definition,
        "_build_embedding_client",
        lambda session, model_ref_id: FakeEmbeddingClient(),
    )
    monkeypatch.setattr(
        definition,
        "ChapterIndexIntegrationService",
        StopsAfterStartingFirstChapterIndexService,
    )

    context = JobContext(
        session=session,
        job=job,
        publisher=BackgroundEventPublisher(),
    )
    context.check_cancelled = _noop_check_cancelled  # type: ignore[method-assign]

    with pytest.raises(JobCancelledError, match="用户停止索引"):
        await definition.handle_retrieval_chapter_index_batch(context)

    await session.refresh(items[0])
    await session.refresh(items[1])
    await session.refresh(items[2])
    assert items[0].status == JOB_STATUS_RUNNING
    assert items[1].status == JOB_STATUS_PENDING
    assert items[2].status == JOB_STATUS_PENDING

    deleted_document_ids: list[str] = []

    class CleanupRetrievalService:
        async def delete_documents(self, session, index_key, document_ids):
            _ = (session, index_key)
            deleted_document_ids.extend(document_ids)

    monkeypatch.setattr(definition, "OpenFicRetrievalService", CleanupRetrievalService)
    monkeypatch.setattr(
        definition.retrieval_chapter_index_state_repo,
        "get_by_project_and_chapter",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("cancellation cleanup must not query chapter states individually")
        ),
    )
    monkeypatch.setattr(
        definition.job_repo,
        "save_item",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("cancellation cleanup must not save items individually")
        ),
    )

    await definition._handle_cancelled(context, "用户停止索引")

    assert deleted_document_ids == ["chapter:chapter-multi-0"]
    for item in items:
        await session.refresh(item)
        assert item.status == JOB_STATUS_CANCELLED
    for state in states:
        await session.refresh(state)
        assert state.status == "needs_rebuild"
        assert state.job_id is None
        assert state.item_id is None
