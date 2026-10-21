"""
Tests for retrieval service.
"""

from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import EncryptionService
from app.models.clients.embedding_client import EmbeddingClientConfigLike
from app.models.repos import model_provider_repo, model_repo
from app.retrieval.service import OpenFicRetrievalService
from app.retrieval.types import (
    FilterableField,
    FilterableFieldType,
    IndexDocument,
    RetrievalIndexContract,
)
from app.settings import settings
from app.storage.models.retrieval_index import RetrievalIndex


@dataclass
class FakeEmbeddingConfig:
    model_id: str
    dimensions: int | None


@dataclass
class FakeEmbeddingResponse:
    embeddings: list[list[float]]
    model: str
    usage: None = None


class FakeEmbeddingClient:
    config: EmbeddingClientConfigLike

    def __init__(self, model_id: str = "test-embedding", dimensions: int = 3):
        self.config = FakeEmbeddingConfig(model_id=model_id, dimensions=dimensions)
        self.embed_calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> FakeEmbeddingResponse:
        self.embed_calls.append(texts)
        return FakeEmbeddingResponse(
            embeddings=[self._embed_text(text) for text in texts],
            model=self.config.model_id,
        )

    async def embed_single(self, text: str) -> list[float]:
        return self._embed_text(text)

    @staticmethod
    def _embed_text(text: str) -> list[float]:
        normalized = text.lower()
        return [
            1.0 if "dragon" in normalized else 0.0,
            1.0 if "hero" in normalized else 0.0,
            1.0 if "guild" in normalized else 0.0,
        ]


class AlwaysFailEmbeddingClient(FakeEmbeddingClient):
    async def embed(self, texts: list[str]) -> FakeEmbeddingResponse:
        raise RuntimeError(f"embedding failed for {texts[0]}")


def _make_contract(embedding_model_ref_id: str) -> RetrievalIndexContract:
    return RetrievalIndexContract(
        embedding_model_ref_id=embedding_model_ref_id,
        embedding_model_id_snapshot="test-embedding",
        embedding_dimensions_snapshot=3,
        distance_metric="cosine",
        chunker_type="recursive_character",
        chunk_size=64,
        chunk_overlap=8,
        filterable_fields=[
            FilterableField(name="project_id", field_type=FilterableFieldType.STRING),
            FilterableField(name="chapter_order", field_type=FilterableFieldType.INTEGER),
        ],
        vector_index_type="ivf_hnsw_sq",
        vector_index_params={"m": 8, "ef_construction": 64},
        fts_index_params={"language": "English", "stem": True},
        schema_version=1,
    )


async def _create_embedding_model(session: AsyncSession):
    encryption_service = EncryptionService(settings.encryption_key)
    encrypted_key = encryption_service.encrypt("test-key")

    provider = await model_provider_repo.create(
        session=session,
        name="Test Provider",
        url="https://openrouter.ai/api/v1",
        api_key_encrypted=encrypted_key,
        provider_type="openrouter",
    )

    model = await model_repo.create(
        session=session,
        name="Embedding Model",
        provider_id=provider.id,
        model_id="test-embedding",
        task_type="embedding",
        dimensions=3,
    )
    await session.commit()
    return model


@pytest.mark.asyncio
async def test_index_documents_replace_existing_document(
    session: AsyncSession, tmp_path: Path
) -> None:
    model = await _create_embedding_model(session)
    service = OpenFicRetrievalService(base_dir=tmp_path / "lancedb")
    contract = _make_contract(model.id)
    embedding_client = FakeEmbeddingClient()

    await service.register_index(session, "chapters", contract)
    await service.index_documents(
        session,
        "chapters",
        [
            IndexDocument(
                document_id="chapter-1",
                text="The hero meets a dragon.",
                attributes={"project_id": "p1", "chapter_order": 1},
            )
        ],
        embedding_client,
    )
    await service.index_documents(
        session,
        "chapters",
        [
            IndexDocument(
                document_id="chapter-1",
                text="The hero leaves the guild behind.",
                attributes={"project_id": "p1", "chapter_order": 1},
            )
        ],
        embedding_client,
    )

    query = await service.query(session, "chapters", "guild", embedding_client)
    results = await query.hybrid().limit(5).run()

    assert [row.document_id for row in results] == ["chapter-1"]
    assert results[0].text == "The hero leaves the guild behind."


@pytest.mark.asyncio
async def test_delete_document_removes_rows(session: AsyncSession, tmp_path: Path) -> None:
    model = await _create_embedding_model(session)
    service = OpenFicRetrievalService(base_dir=tmp_path / "lancedb")
    contract = _make_contract(model.id)
    embedding_client = FakeEmbeddingClient()

    await service.register_index(session, "chapters", contract)
    await service.index_documents(
        session,
        "chapters",
        [
            IndexDocument(
                document_id="chapter-1",
                text="The hero meets a dragon.",
                attributes={"project_id": "p1", "chapter_order": 1},
            )
        ],
        embedding_client,
    )

    await service.delete_document(session, "chapters", "chapter-1")

    query = await service.query(session, "chapters", "dragon", embedding_client)
    results = await query.hybrid().limit(5).run()

    assert results == []


@pytest.mark.asyncio
async def test_rebuild_replaces_table_contents(session: AsyncSession, tmp_path: Path) -> None:
    model = await _create_embedding_model(session)
    service = OpenFicRetrievalService(base_dir=tmp_path / "lancedb")
    contract = _make_contract(model.id)
    embedding_client = FakeEmbeddingClient()

    await service.register_index(session, "chapters", contract)
    await service.index_documents(
        session,
        "chapters",
        [
            IndexDocument(
                document_id="chapter-1",
                text="The hero meets a dragon.",
                attributes={"project_id": "p1", "chapter_order": 1},
            )
        ],
        embedding_client,
    )

    await service.rebuild(
        session,
        "chapters",
        [
            IndexDocument(
                document_id="chapter-2",
                text="A quiet village watches the guild parade.",
                attributes={"project_id": "p1", "chapter_order": 2},
            )
        ],
        embedding_client,
    )

    query = await service.query(session, "chapters", "guild", embedding_client)
    results = await query.hybrid().limit(5).run()

    assert [row.document_id for row in results] == ["chapter-2"]


@pytest.mark.asyncio
async def test_index_documents_can_retry_after_failed_status(
    session: AsyncSession, tmp_path: Path
) -> None:
    model = await _create_embedding_model(session)
    service = OpenFicRetrievalService(base_dir=tmp_path / "lancedb")
    contract = _make_contract(model.id)

    await service.register_index(session, "chapters", contract)
    failed_result = await service.index_documents(
        session,
        "chapters",
        [IndexDocument(document_id="chapter-1", text="dragon")],
        AlwaysFailEmbeddingClient(),
    )
    row = (await session.execute(select(RetrievalIndex))).scalar_one()
    assert failed_result.failed_count == 1
    assert row.status == "failed"

    retry_result = await service.index_documents(
        session,
        "chapters",
        [
            IndexDocument(
                document_id="chapter-1",
                text="The hero meets a dragon.",
                attributes={"project_id": "p1", "chapter_order": 1},
            )
        ],
        FakeEmbeddingClient(),
    )

    await session.refresh(row)
    assert retry_result.succeeded_count == 1
    assert row.status == "ready"
