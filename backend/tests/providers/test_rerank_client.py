"""
Tests for RerankClient.
"""

import pytest
import respx
from httpx import Response

from app.core.errors import ValidationError
from app.models.clients.rerank_client import RerankClient, RerankConfig


def _make_client() -> RerankClient:
    return RerankClient(
        RerankConfig(
            provider_type="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_key="test-key",
            model_id="test-reranker",
        )
    )


@pytest.mark.asyncio
@respx.mock
async def test_rerank_parses_response_and_sends_top_n() -> None:
    route = respx.post("https://openrouter.ai/api/v1/rerank").mock(
        return_value=Response(
            200,
            json={
                "model": "test-reranker",
                "results": [
                    {"index": 1, "relevance_score": 0.91},
                    {"index": 0, "relevance_score": 0.62},
                ],
                "usage": {"total_tokens": 42},
            },
        )
    )

    client = _make_client()
    response = await client.rerank(
        "hero betrays the guild",
        ["the guild trusted the hero", "the hero betrays the guild"],
        top_n=1,
    )

    assert route.called
    assert route.calls[0].request.headers["authorization"] == "Bearer test-key"
    assert route.calls[0].request.read() == (
        b'{"model":"test-reranker","query":"hero betrays the guild",'
        b'"documents":["the guild trusted the hero","the hero betrays the guild"],'
        b'"top_n":1}'
    )
    assert response.model == "test-reranker"
    assert response.usage == {"total_tokens": 42}
    assert [(item.index, item.relevance_score) for item in response.results] == [
        (1, 0.91),
        (0, 0.62),
    ]


@pytest.mark.asyncio
@respx.mock
async def test_rerank_raises_validation_error_for_out_of_range_index() -> None:
    respx.post("https://openrouter.ai/api/v1/rerank").mock(
        return_value=Response(
            200,
            json={"results": [{"index": 2, "relevance_score": 0.9}]},
        )
    )

    client = _make_client()

    with pytest.raises(ValidationError):
        await client.rerank("query", ["doc 1"])
