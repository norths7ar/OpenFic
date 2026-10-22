"""Anthropic-compatible provider adapter."""

from collections.abc import Mapping

import httpx

from app.models.adapters.base import BaseAdapter
from app.models.adapters.model_list import parse_model_list


class AnthropicCompatibleAdapter(BaseAdapter):
    """Anthropic-compatible provider adapter supporting LLM calls only."""

    @property
    def provider_type(self) -> str:
        return "anthropic-compatible"

    def supports_embedding(self) -> bool:
        return False

    async def get_llm_models(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> list[dict[str, str]]:
        url = self._normalize_url(base_url)
        for suffix in ("/anthropic", "/claude"):
            if url.endswith(suffix):
                url = url.removesuffix(suffix)
                break
        if not url.endswith("/v1"):
            url = f"{url}/v1"

        request_headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        request_headers.update(headers or {})
        response = await client.get(
            f"{url}/models",
            headers=request_headers,
        )
        response.raise_for_status()
        return [
            {**model, "name": model.get("display_name") or model["name"]}
            for model in parse_model_list(response.json())
        ]

    async def get_embedding_models(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> list[dict[str, str]]:
        return []
