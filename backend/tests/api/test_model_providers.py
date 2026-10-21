"""
ModelProvider API Tests - 模型服务提供商 API 测试。
"""


import httpx
import pytest
import respx
from httpx import AsyncClient

_OPENAI_ICON_URL = "/icons/model/catalog/openai.svg"
_OPENROUTER_ICON_URL = "/icons/model/catalog/openrouter.svg"


@pytest.mark.asyncio
@respx.mock
async def test_validate_openai_responses_compatible_provider_discovers_models(
    client: AsyncClient,
):
    route = respx.get("https://gateway.example/v1/models").mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"id": "responses-model", "name": "Responses Model"}]},
        )
    )

    response = await client.post(
        "/api/v1/model-providers/validate",
        json={
            "provider_type": "openai-compatible-responses",
            "url": "https://gateway.example",
            "api_key": "test-key",
            "custom_headers": [{"key": "X-Provider-Token", "value": "custom-token"}],
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["models"] == [
        {
            "id": "responses-model",
            "name": "Responses Model",
            "task_type": None,
            "metadata": None,
        }
    ]
    assert route.calls[0].request.headers["authorization"] == "Bearer test-key"
    assert route.calls[0].request.headers["x-provider-token"] == "custom-token"
