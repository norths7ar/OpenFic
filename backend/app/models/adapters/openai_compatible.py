"""
OpenAI Compatible Adapter - OpenAI兼容API适配器。

用于支持各种OpenAI兼容的第三方服务（如Ollama、vLLM等）。
由于是通用兼容接口，无法区分LLM和Embedding，两个方法都返回全部模型列表。
"""

from collections.abc import Mapping
from typing import Any

import httpx

from app.models.adapters.base import BaseAdapter
from app.models.adapters.model_list import parse_model_list


class OpenAICompatibleAdapter(BaseAdapter):
    """OpenAI兼容API适配器，支持LLM和Embedding。"""

    @property
    def provider_type(self) -> str:
        return "openai-compatible"

    async def get_llm_models(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """获取模型列表（返回全部可用模型）。"""
        return await self._fetch_all_models(
            client, base_url, api_key, headers=headers, validate_directory=True
        )

    async def get_embedding_models(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """获取模型列表（返回全部可用模型，由用户自行选择）。"""
        return await self._fetch_all_models(client, base_url, api_key, headers=headers)

    async def get_rerank_models(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """获取模型列表（返回全部可用模型，由用户自行选择）。"""
        return await self._fetch_all_models(client, base_url, api_key, headers=headers)

    def supports_rerank(self) -> bool:
        return True

    async def _fetch_all_models(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        *,
        headers: Mapping[str, str] | None = None,
        validate_directory: bool = False,
    ) -> list[dict[str, Any]]:
        """获取所有可用模型。"""
        url = self._normalize_url(base_url)
        url = f"{url}/models" if url.endswith("/v1") else f"{url}/v1/models"
        request_headers = self._build_auth_header(api_key, headers)

        response = await client.get(url, headers=request_headers)
        response.raise_for_status()
        if validate_directory:
            return parse_model_list(response.json())
        # Preserve the existing embedding/rerank list behavior outside LLM discovery.
        return [
            {**model, "name": model.get("name") or model["id"]}
            for model in response.json().get("data", [])
            if isinstance(model, dict) and isinstance(model.get("id"), str)
        ]
