"""Project chapter retrieval index API tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.background.jobs.models import BackgroundJob, BackgroundJobItem
from app.background.jobs.states import JOB_STATUS_CANCELLED
from app.background.runtime.supervisor import get_background_supervisor
from app.core.encryption import EncryptionService
from app.models.repos import model_provider_repo, model_repo
from app.storage.repos import retrieval_chapter_index_state_repo, setting_repo


async def _create_project(client: AsyncClient) -> tuple[str, str]:
    response = await client.post("/api/v1/projects", data={"title": "检索测试"})
    assert response.status_code == 201
    project_id = response.json()["id"]
    volumes = (await client.get(f"/api/v1/projects/{project_id}/volumes")).json()
    return project_id, volumes[0]["id"]


async def _create_chapter(
    client: AsyncClient,
    project_id: str,
    volume_id: str,
    *,
    title: str,
    content: str = "正文",
) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/chapters",
        json={"volume_id": volume_id, "title": title, "content": content},
    )
    assert response.status_code == 201
    return response.json()


async def _create_embedding_model(session: AsyncSession):
    from app.settings import settings

    encryption_service = EncryptionService(settings.encryption_key)
    provider = await model_provider_repo.create(
        session=session,
        name="Embedding Provider",
        url="https://api.test.com",
        api_key_encrypted=encryption_service.encrypt("test-key"),
        provider_type="openai",
    )
    model = await model_repo.create(
        session=session,
        name="Embedding Model",
        provider_id=provider.id,
        model_id="text-embedding-test",
        task_type="embedding",
        dimensions=3,
    )
    await setting_repo.upsert(session, "default_embedding_model", model.id)
    await session.commit()
    return model


@pytest.mark.asyncio
async def test_index_stop_cancels_pending_job_and_resets_incomplete_chapters(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    from sqlalchemy import select
    from sqlmodel import col

    await _create_embedding_model(session)
    project_id, volume_id = await _create_project(client)
    chapter = await _create_chapter(client, project_id, volume_id, title="一章")
    await setting_repo.upsert(session, "index_mode", "all")
    await session.commit()

    start_response = await client.post(f"/api/v1/projects/{project_id}/retrieval/index/start")
    assert start_response.status_code == 200

    response = await client.post(f"/api/v1/projects/{project_id}/retrieval/index/stop")

    assert response.status_code == 200
    assert response.json() == {"project_id": project_id, "stopped_count": 1}
    job = (
        await session.execute(
            select(BackgroundJob).where(col(BackgroundJob.subject_id) == project_id)
        )
    ).scalar_one()
    item = (
        await session.execute(
            select(BackgroundJobItem).where(col(BackgroundJobItem.job_id) == job.id)
        )
    ).scalar_one()
    chapter_state = await retrieval_chapter_index_state_repo.get_by_project_and_chapter(
        session,
        project_id=project_id,
        chapter_id=chapter["id"],
        index_key=f"chapters:{project_id}",
    )

    assert job.status == JOB_STATUS_CANCELLED
    assert item.status == JOB_STATUS_CANCELLED
    assert chapter_state is not None
    assert chapter_state.status == "needs_rebuild"
    assert chapter_state.job_id is None
    assert chapter_state.item_id is None
    assert chapter_state.error_message is None


@pytest.mark.asyncio
async def test_background_cancel_interrupts_running_index_job(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = BackgroundJob(
        type="retrieval_chapter_index_batch",
        status="running",
        payload_json='{"project_id":"test"}',
    )
    session.add(job)
    await session.commit()

    interrupted_job_ids: list[str] = []
    monkeypatch.setattr(
        get_background_supervisor(),
        "cancel_running_index_batch",
        interrupted_job_ids.append,
    )

    response = await client.post(f"/api/v1/background/jobs/{job.id}/cancel", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "cancel_requested"
    assert interrupted_job_ids == [job.id]


@pytest.mark.asyncio
async def test_index_stop_is_idempotent_without_an_active_job(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    await _create_embedding_model(session)
    project_id, _ = await _create_project(client)

    response = await client.post(f"/api/v1/projects/{project_id}/retrieval/index/stop")

    assert response.status_code == 200
    assert response.json() == {"project_id": project_id, "stopped_count": 0}
