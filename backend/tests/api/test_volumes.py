"""
Volume API tests.
"""


import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.retrieval.chapter_index import compute_chapter_source_hash
from app.storage.models.retrieval_chapter_index_state import RetrievalChapterIndexState


async def _create_project(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/projects",
        data={"title": "测试小说"},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _default_volume(client: AsyncClient, project_id: str) -> dict:
    response = await client.get(f"/api/v1/projects/{project_id}/volumes")
    assert response.status_code == 200
    volumes = response.json()
    assert len(volumes) == 1
    return volumes[0]


@pytest.mark.asyncio
async def test_move_chapter_to_volume_marks_retrieval_state_stale(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    project_id = await _create_project(client)
    source_volume = await _default_volume(client, project_id)
    target_response = await client.post(
        f"/api/v1/projects/{project_id}/volumes",
        json={"title": "第二卷"},
    )
    target_volume = target_response.json()
    chapter_response = await client.post(
        f"/api/v1/projects/{project_id}/chapters",
        json={
            "volume_id": source_volume["id"],
            "title": "第一章",
            "content": "正文",
        },
    )
    chapter = chapter_response.json()
    state = RetrievalChapterIndexState(
        project_id=project_id,
        chapter_id=chapter["id"],
        index_key=f"chapters:{project_id}",
        status="ready",
        source_hash=compute_chapter_source_hash(chapter["content"]),
        embedding_model_ref_id="model-1",
        chunk_count=1,
    )
    session.add(state)
    await session.commit()

    response = await client.post(
        f"/api/v1/chapters/{chapter['id']}/move-to-volume",
        json={"volume_id": target_volume["id"]},
    )

    assert response.status_code == 200
    await session.refresh(state)
    assert state.status == "stale"
