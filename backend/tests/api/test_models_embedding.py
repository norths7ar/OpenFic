"""
Tests for Model API endpoints - Embedding支持测试。
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.repos import model_provider_repo, model_repo
from app.retrieval.service import OpenFicRetrievalService
from app.retrieval.types import RetrievalIndexContract


@pytest.mark.asyncio
async def test_update_bound_embedding_model_dimensions_is_forbidden(
    client: AsyncClient, session: AsyncSession, tmp_path
):
    from app.core.encryption import EncryptionService
    from app.settings import settings

    encryption_service = EncryptionService(settings.encryption_key)
    encrypted_key = encryption_service.encrypt("test-key")

    provider = await model_provider_repo.create(
        session=session,
        name="Test Provider",
        url="https://api.test.com",
        api_key_encrypted=encrypted_key,
        provider_type="openai",
    )

    model = await model_repo.create(
        session=session,
        name="Bound Embedding Model",
        provider_id=provider.id,
        model_id="text-embedding-3-small",
        task_type="embedding",
        dimensions=1536,
    )
    await session.commit()

    retrieval = OpenFicRetrievalService(base_dir=tmp_path / "lancedb")
    await retrieval.register_index(
        session,
        "bound-index",
        RetrievalIndexContract(
            embedding_model_ref_id=model.id,
            embedding_model_id_snapshot="text-embedding-3-small",
            embedding_dimensions_snapshot=1536,
            distance_metric="cosine",
            chunker_type="recursive_character",
            chunk_size=128,
            chunk_overlap=16,
            filterable_fields=[],
            vector_index_type="ivf_hnsw_sq",
            vector_index_params={},
            fts_index_params={},
            schema_version=1,
        ),
    )
    await session.commit()

    response = await client.put(
        f"/api/v1/models/{model.id}",
        json={"dimensions": 3072},
    )

    assert response.status_code == 400
    assert "bound to retrieval indexes" in response.json()["detail"]
