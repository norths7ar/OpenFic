"""章节导出 API 测试。"""

from urllib.parse import unquote

import pytest
from httpx import AsyncClient

from app.background.events.publisher import BackgroundEventPublisher
from app.background.jobs import service as background_service
from app.background.runtime.context import JobContext
from app.background.runtime.dispatcher import dispatch_job
from app.chapter_export import service as chapter_export_service


async def _create_project(client: AsyncClient, title: str = "测试小说") -> tuple[str, str]:
    response = await client.post("/api/v1/projects", data={"title": title})
    assert response.status_code == 201
    project_id = response.json()["id"]
    volumes = (await client.get(f"/api/v1/projects/{project_id}/volumes")).json()
    return project_id, volumes[0]["id"]


async def _create_chapter(
    client: AsyncClient,
    project_id: str,
    volume_id: str,
    title: str,
    content: str,
    word_count: int,
) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/chapters",
        json={
            "volume_id": volume_id,
            "title": title,
            "content": content,
            "word_count": word_count,
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_export_task_writes_full_volume_txt_and_serves_download(
    client: AsyncClient,
    session,
    monkeypatch,
    tmp_path,
) -> None:
    async def skip_cancellation_check(_context: JobContext) -> None:
        return None

    monkeypatch.setattr(chapter_export_service.settings, "chapter_exports_dir", tmp_path)
    monkeypatch.setattr(JobContext, "check_cancelled", skip_cancellation_check)
    project_id, volume_id = await _create_project(client)
    first = await _create_chapter(
        client, project_id, volume_id, "第一章", "第一章正文\r\n第二行", 5
    )
    second = await _create_chapter(client, project_id, volume_id, "第二章", "第二章正文", 5)
    created = await client.post(
        f"/api/v1/projects/{project_id}/chapter-exports",
        json={
            "selected_volume_ids": [volume_id],
            "included_chapter_ids": [],
            "excluded_chapter_ids": [],
            "local_date": "2026-07-28",
        },
    )
    assert created.status_code == 201
    job = await background_service.get_job(session, created.json()["id"])
    assert job is not None
    job.status = "running"
    await session.commit()

    context = JobContext(session=session, job=job, publisher=BackgroundEventPublisher(None))
    result = await dispatch_job(context)
    await background_service.mark_succeeded(session, context.publisher, context.job, result=result)
    await session.commit()

    status_response = await client.get(f"/api/v1/projects/{project_id}/chapter-exports/{job.id}")
    assert status_response.status_code == 200
    assert status_response.json()["current"] == 2
    assert status_response.json()["total"] == 2
    assert status_response.json()["download_url"]

    download_response = await client.get(
        f"/api/v1/projects/{project_id}/chapter-exports/{job.id}/download"
    )
    assert download_response.status_code == 200
    assert "attachment" in download_response.headers["content-disposition"]
    assert "测试小说-全本-2026-07-28.txt" in unquote(
        download_response.headers["content-disposition"]
    )
    assert download_response.content.decode("utf-8-sig") == (
        "第一卷 第一卷\n第一章\n第一章正文\n第二行\n\n第二章\n第二章正文"
    )
    assert result == {
        "filename": "测试小说-全本-2026-07-28.txt",
        "volume_count": 1,
        "chapter_count": 2,
        "word_count": 10,
        "expires_at": result["expires_at"],
    }
    assert [first["id"], second["id"]] == created.json()["chapter_ids"]
