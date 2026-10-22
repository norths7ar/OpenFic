"""Tests for Chapter Context API."""

import pytest
from httpx import AsyncClient

from app.api.routers.chapter_context import (
    build_summary_statuses_response,
)
from app.memory.chapter.summary_service import (
    normalize_summary_source_content,
)
from app.storage.models.chapter_summary import ChapterSummary
from app.storage.repos.chapter_summary_repo import (
    SUMMARY_STATUS_READY,
)


class _FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload


async def _summary_statuses_response(session, project_id: str) -> _FakeResponse:
    statuses = await build_summary_statuses_response(session, project_id)
    return _FakeResponse([item.model_dump(mode="json") for item in statuses])


def _source_content(chapter: dict) -> str:
    return normalize_summary_source_content(chapter["content"])


async def _default_volume_id(client: AsyncClient, project_id: str) -> str:
    response = await client.get(f"/api/v1/projects/{project_id}/volumes")
    assert response.status_code == 200
    volumes = response.json()
    assert len(volumes) == 1
    return volumes[0]["id"]


@pytest.fixture
async def test_project(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/v1/projects",
        data={"title": "Context Test Project", "description": "Test project"},
    )
    assert response.status_code == 201
    project = response.json()
    project["default_volume_id"] = await _default_volume_id(client, project["id"])
    return project


@pytest.fixture
async def test_chapters(client: AsyncClient, test_project: dict) -> list[dict]:
    chapters = []
    for i in range(5):
        response = await client.post(
            f"/api/v1/projects/{test_project['id']}/chapters",
            json={
                "volume_id": test_project["default_volume_id"],
                "title": f"第{i + 1}章",
                "content": f"这是第{i + 1}章的内容。" * 50,
                "word_count": 800,
            },
        )
        assert response.status_code == 201
        chapters.append(response.json())
    return chapters


@pytest.mark.asyncio
class TestChapterSummaries:
    async def test_summary_stale_is_dynamic_by_content_diff(
        self, client: AsyncClient, session, test_project: dict, test_chapters: list[dict]
    ):
        chapter = test_chapters[0]
        session.add(
            ChapterSummary(
                project_id=test_project["id"],
                summary_type="chapter",
                status=SUMMARY_STATUS_READY,
                chapter_id=chapter["id"],
                chapter_order=chapter["order"],
                start_order=chapter["order"],
                end_order=chapter["order"],
                summary="旧摘要",
                source_content_normalized=_source_content(chapter),
            )
        )
        await session.commit()

        response = await client.patch(
            f"/api/v1/chapters/{chapter['id']}",
            json={
                "content": f"{chapter['content']}{'新增剧情' * 40}",
                "word_count": 1200,
            },
        )
        assert response.status_code == 200

        status_response = await _summary_statuses_response(session, test_project["id"])
        item = next(item for item in status_response.json() if item["chapter_id"] == chapter["id"])
        assert item["status"] == "ready"
        assert item["is_stale"] is True

        response = await client.patch(
            f"/api/v1/chapters/{chapter['id']}",
            json={"content": chapter["content"], "word_count": chapter["word_count"]},
        )
        assert response.status_code == 200
        status_response = await _summary_statuses_response(session, test_project["id"])
        item = next(item for item in status_response.json() if item["chapter_id"] == chapter["id"])
        assert item["status"] == "ready"
        assert item["is_stale"] is False
