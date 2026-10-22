"""
DeepSeek Adapter - DeepSeek API适配器。

DeepSeek API兼容OpenAI格式，仅支持LLM，不支持Embedding。
"""

from collections.abc import Mapping
from typing import Any

import httpx

from app.models.adapters.base import BaseAdapter


class DeepSeekAdapter(BaseAdapter):
    """DeepSeek API适配器，仅支持LLM。"""

    @property
    def provider_type(self) -> str:
        return "deepseek"

    def supports_embedding(self) -> bool:
        """DeepSeek不支持Embedding。"""
        return False

    async def get_llm_models(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """获取LLM模型列表。"""
        url = f"{self._normalize_url(base_url)}/models"
        request_headers = self._build_auth_header(api_key, headers)
        response = await client.get(url, headers=request_headers)
        response.raise_for_status()
        return [
            {**model, "name": model.get("name") or model["id"]}
            for model in response.json().get("data", [])
            if isinstance(model, dict) and isinstance(model.get("id"), str)
        ]

    async def get_embedding_models(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> list[dict[str, str]]:
        """DeepSeek不支持Embedding模型。"""
        return []
