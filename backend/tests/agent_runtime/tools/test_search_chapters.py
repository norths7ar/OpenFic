import importlib
import json
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import EncryptionService
from app.models.repos import model_provider_repo, model_repo
from app.retrieval.chapter_index import compute_chapter_source_hash
from app.retrieval.types import ChunkSearchResult
from app.settings import settings
from app.storage.models.chapter import Chapter
from app.storage.models.project import Project
from app.storage.models.project_folder import ProjectFolder as Volume
from app.storage.models.retrieval_chapter_index_state import (
    RetrievalChapterIndexState,
)
from app.storage.models.retrieval_index import RetrievalIndex
from app.storage.repos import setting_repo


@dataclass
class FakeEmbeddingClient:
    config: Any


class FakeQueryBuilder:
    def __init__(self, results: list[ChunkSearchResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, Any]] = []

    def hybrid(self):
        self.calls.append(("hybrid", None))
        return self

    def vector(self):
        self.calls.append(("vector", None))
        return self

    def bm25(self):
        self.calls.append(("bm25", None))
        return self

    def vector_top_k(self, count: int):
        self.calls.append(("vector_top_k", count))
        return self

    def bm25_top_k(self, count: int):
        self.calls.append(("bm25_top_k", count))
        return self

    def rrf(self, *, k: int):
        self.calls.append(("rrf", k))
        return self

    def rerank(self, rerank_client, *, top_n=None):
        self.calls.append(("rerank", (rerank_client, top_n)))
        return self

    def ef(self, ef: int):
        self.calls.append(("ef", ef))
        return self

    def filter_eq(self, field: str, value: Any):
        self.calls.append(("filter_eq", (field, value)))
        return self

    def limit(self, count: int):
        self.calls.append(("limit", count))
        return self

    async def run(self) -> list[ChunkSearchResult]:
        self.calls.append(("run", None))
        return self.results


class FakeRetrievalService:
    def __init__(self, results: list[ChunkSearchResult]) -> None:
        self.results = results
        self.queries: list[tuple[str, str]] = []
        self.last_builder: FakeQueryBuilder | None = None

    async def query(self, session, index_key: str, text: str, embedding_client):
        _ = (session, embedding_client)
        self.queries.append((index_key, text))
        self.last_builder = FakeQueryBuilder(self.results)
        return self.last_builder


class FailingQueryRetrievalService:
    def __init__(
        self,
        message: str,
        error_type: type[Exception] = RuntimeError,
    ) -> None:
        self.message = message
        self.error_type = error_type
        self.queries: list[tuple[str, str]] = []

    async def query(self, session, index_key: str, text: str, embedding_client):
        _ = (session, embedding_client)
        self.queries.append((index_key, text))
        raise self.error_type(self.message)


def _make_state(project_id: str = "project-search") -> dict[str, Any]:
    return {
        "session_id": "session-search",
        "project_id": project_id,
        "model_config": {},
        "active_agent": None,
        "is_completed": False,
        "error": None,
        "retry_count": 0,
        "message_checkpoints": [],
        "user_request": "",
    }


def _make_search_chapters_tool(module):
    return module.SearchChaptersTool(_state=_make_state())


async def _create_project_with_chapters(
    session: AsyncSession,
    *,
    project_id: str = "project-search",
) -> tuple[Chapter, Chapter]:
    project = Project(id=project_id, title="检索项目")
    volume = Volume(
        scope="writing", id="volume-main", project_id=project.id, title="第一卷", order=1
    )
    ready_chapter = Chapter(
        id="chapter-ready",
        project_id=project.id,
        volume_id=volume.id,
        title="星桥",
        content="星桥旧文本",
        order=1,
        word_count=5,
    )
    stale_chapter = Chapter(
        id="chapter-stale",
        project_id=project.id,
        volume_id=volume.id,
        title="潮汐",
        content="潮汐新文本",
        order=2,
        word_count=6,
    )
    session.add(project)
    session.add(volume)
    session.add(ready_chapter)
    session.add(stale_chapter)
    await session.flush()
    return ready_chapter, stale_chapter


async def _create_embedding_model(
    session: AsyncSession,
    *,
    model_id: str = "text-embedding-test",
    task_type: str = "embedding",
    dimensions: int | None = 3,
):
    encryption = EncryptionService(settings.encryption_key)
    provider = await model_provider_repo.create(
        session,
        name="Embedding Provider",
        url="https://example.test/v1",
        api_key_encrypted=encryption.encrypt("secret"),
        provider_type="openai-compatible",
    )
    return await model_repo.create(
        session,
        name="Embedding Model",
        provider_id=provider.id,
        model_id=model_id,
        task_type=task_type,
        dimensions=dimensions,
    )


def _chunk(
    *,
    chapter_id: str,
    chunk_id: str,
    chunk_index: int,
    text: str,
    score: float,
    matched_by: str = "hybrid",
) -> ChunkSearchResult:
    return ChunkSearchResult(
        document_id=f"chapter:{chapter_id}",
        chunk_id=chunk_id,
        chunk_index=chunk_index,
        text=text,
        metadata={
            "project_id": "project-search",
            "chapter_id": chapter_id,
            "volume_id": "metadata-volume",
            "chapter_title": "metadata-title",
        },
        score=score,
        matched_by=matched_by,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("index_status", ["registered", "needs_rebuild"])
async def test_search_chapters_returns_text_when_project_index_is_not_ready(
    session: AsyncSession,
    index_status: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("app.agent_runtime.tools.impls.chapter.search_chapters")

    model = await _create_embedding_model(session)
    await _create_project_with_chapters(session)
    session.add(
        RetrievalIndex(
            index_key="chapters:project-search",
            table_name="chapters_project_search",
            status=index_status,
            embedding_model_ref_id=model.id,
            embedding_model_id_snapshot=model.model_id,
            embedding_dimensions_snapshot=3,
            schema_version=2,
        )
    )
    session.add(
        RetrievalChapterIndexState(
            project_id="project-search",
            chapter_id="chapter-ready",
            index_key="chapters:project-search",
            status="ready",
            source_hash="hash-ready",
            embedding_model_ref_id=model.id,
            chunk_count=1,
        )
    )
    await setting_repo.upsert(session, "default_embedding_model", model.id)
    await session.commit()
    retrieval = FakeRetrievalService(
        [
            _chunk(
                chapter_id="chapter-ready",
                chunk_id="c1",
                chunk_index=0,
                text="old",
                score=0.5,
            )
        ]
    )
    monkeypatch.setattr(module, "OpenFicRetrievalService", lambda: retrieval)
    monkeypatch.setattr(module, "EmbeddingClient", FakeEmbeddingClient)

    tool = _make_search_chapters_tool(module)
    result = await tool.ainvoke(
        {"query": "星桥"},
        config={"configurable": {"db_session": session}},
    )

    # 索引不可用时返回提示文本（非 JSON），且不执行检索。
    assert "索引" in result
    assert "更新" in result
    assert retrieval.queries == []


@pytest.mark.asyncio
async def test_search_chapters_skips_chunks_for_other_project_chapters(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("app.agent_runtime.tools.impls.chapter.search_chapters")

    model = await _create_embedding_model(session)
    await _create_project_with_chapters(session)
    other_project = Project(id="project-other", title="其它项目")
    other_volume = Volume(
        scope="writing",
        id="volume-other",
        project_id=other_project.id,
        title="其它卷",
        order=1,
    )
    other_chapter = Chapter(
        id="chapter-other",
        project_id=other_project.id,
        volume_id=other_volume.id,
        title="不应泄露",
        content="跨项目正文",
        order=1,
        word_count=4,
    )
    session.add(other_project)
    session.add(other_volume)
    session.add(other_chapter)
    session.add(
        RetrievalIndex(
            index_key="chapters:project-search",
            table_name="chapters_project_search",
            status="ready",
            embedding_model_ref_id=model.id,
            embedding_model_id_snapshot=model.model_id,
            embedding_dimensions_snapshot=3,
            schema_version=2,
        )
    )
    session.add_all(
        [
            RetrievalChapterIndexState(
                project_id="project-search",
                chapter_id="chapter-ready",
                index_key="chapters:project-search",
                status="ready",
                source_hash="hash-ready",
                embedding_model_ref_id=model.id,
                chunk_count=1,
            ),
            RetrievalChapterIndexState(
                project_id="project-other",
                chapter_id="chapter-other",
                index_key="chapters:project-other",
                status="ready",
                source_hash="hash-other",
                embedding_model_ref_id=model.id,
                chunk_count=1,
            ),
        ]
    )
    await setting_repo.upsert(session, "default_embedding_model", model.id)
    await session.commit()
    retrieval = FakeRetrievalService(
        [
            _chunk(
                chapter_id="chapter-ready",
                chunk_id="ready:0",
                chunk_index=0,
                text="当前项目结果",
                score=0.9,
            ),
            _chunk(
                chapter_id="chapter-other",
                chunk_id="other:0",
                chunk_index=0,
                text="跨项目结果",
                score=0.95,
            ),
        ]
    )
    monkeypatch.setattr(module, "OpenFicRetrievalService", lambda: retrieval)
    monkeypatch.setattr(module, "EmbeddingClient", FakeEmbeddingClient)

    tool = _make_search_chapters_tool(module)
    data = json.loads(
        await tool.ainvoke(
            {"query": "项目", "force": True},
            config={"configurable": {"db_session": session}},
        )
    )

    assert [item["chapter_title"] for item in data["results"]] == ["星桥"]
    assert "不应泄露" not in json.dumps(data, ensure_ascii=False)


@pytest.mark.asyncio
async def test_search_chapters_blocks_when_default_embedding_model_mismatches_index(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("app.agent_runtime.tools.impls.chapter.search_chapters")

    old_model = await _create_embedding_model(session, model_id="old-embedding")
    new_model = await _create_embedding_model(session, model_id="new-embedding")
    await _create_project_with_chapters(session)
    session.add(
        RetrievalIndex(
            index_key="chapters:project-search",
            table_name="chapters_project_search",
            status="ready",
            embedding_model_ref_id=old_model.id,
            embedding_model_id_snapshot=old_model.model_id,
            embedding_dimensions_snapshot=3,
            schema_version=2,
        )
    )
    session.add(
        RetrievalChapterIndexState(
            project_id="project-search",
            chapter_id="chapter-ready",
            index_key="chapters:project-search",
            status="ready",
            source_hash="hash-ready",
            embedding_model_ref_id=old_model.id,
            chunk_count=1,
        )
    )
    await setting_repo.upsert(session, "default_embedding_model", new_model.id)
    await session.commit()
    retrieval = FakeRetrievalService([])
    monkeypatch.setattr(module, "OpenFicRetrievalService", lambda: retrieval)
    monkeypatch.setattr(module, "EmbeddingClient", FakeEmbeddingClient)

    tool = _make_search_chapters_tool(module)
    result = await tool.ainvoke(
        {"query": "星桥"},
        config={"configurable": {"db_session": session}},
    )

    assert "更新索引" in result
    assert retrieval.queries == []


@pytest.mark.asyncio
async def test_search_chapters_blocks_when_embedding_dimensions_mismatch_index(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("app.agent_runtime.tools.impls.chapter.search_chapters")

    model = await _create_embedding_model(session, dimensions=5)
    await _create_project_with_chapters(session)
    session.add(
        RetrievalIndex(
            index_key="chapters:project-search",
            table_name="chapters_project_search",
            status="ready",
            embedding_model_ref_id=model.id,
            embedding_model_id_snapshot=model.model_id,
            embedding_dimensions_snapshot=3,
            schema_version=2,
        )
    )
    session.add(
        RetrievalChapterIndexState(
            project_id="project-search",
            chapter_id="chapter-ready",
            index_key="chapters:project-search",
            status="ready",
            source_hash="hash-ready",
            embedding_model_ref_id=model.id,
            chunk_count=1,
        )
    )
    await setting_repo.upsert(session, "default_embedding_model", model.id)
    await session.commit()
    retrieval = FakeRetrievalService([])
    monkeypatch.setattr(module, "OpenFicRetrievalService", lambda: retrieval)
    monkeypatch.setattr(module, "EmbeddingClient", FakeEmbeddingClient)

    tool = _make_search_chapters_tool(module)
    result = await tool.ainvoke(
        {"query": "星桥"},
        config={"configurable": {"db_session": session}},
    )

    assert "更新索引" in result
    assert retrieval.queries == []


@pytest.mark.asyncio
async def test_search_chapters_preserves_index_not_ready_reason(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.retrieval.service import IndexNotReadyError

    module, _ = await _seed_ready_index(session)
    reason = "Index chapters:project-search is not ready"
    retrieval = FailingQueryRetrievalService(reason, error_type=IndexNotReadyError)
    monkeypatch.setattr(module, "OpenFicRetrievalService", lambda: retrieval)
    monkeypatch.setattr(module, "EmbeddingClient", FakeEmbeddingClient)

    tool = _make_search_chapters_tool(module)
    data = json.loads(
        await tool.ainvoke(
            {"query": "星桥", "force": True},
            config={"configurable": {"db_session": session}},
        )
    )

    assert data["type"] == "fail"
    assert data["message"] == f"章节检索执行失败: {reason}"


async def _seed_ready_index(session: AsyncSession) -> Any:
    """构造一个 fresh 可检索的项目索引，返回 (module, retrieval, model)。"""
    module = importlib.import_module("app.agent_runtime.tools.impls.chapter.search_chapters")
    model = await _create_embedding_model(session)
    await _create_project_with_chapters(session)
    session.add(
        RetrievalIndex(
            index_key="chapters:project-search",
            table_name="chapters_project_search",
            status="ready",
            embedding_model_ref_id=model.id,
            embedding_model_id_snapshot=model.model_id,
            embedding_dimensions_snapshot=3,
            schema_version=2,
        )
    )
    session.add(
        RetrievalChapterIndexState(
            project_id="project-search",
            chapter_id="chapter-ready",
            index_key="chapters:project-search",
            status="ready",
            source_hash=compute_chapter_source_hash("星桥旧文本"),
            embedding_model_ref_id=model.id,
            chunk_count=1,
        )
    )
    await setting_repo.upsert(session, "default_embedding_model", model.id)
    return module, model
