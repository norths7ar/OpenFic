"""
OpenAI Adapter - OpenAI API适配器。
"""

from collections.abc import Mapping

import httpx
from loguru import logger

from app.models.adapters.base import BaseAdapter
from app.models.adapters.model_list import parse_model_list


class OpenAIAdapter(BaseAdapter):
    """OpenAI API适配器，支持LLM和Embedding模型。"""

    @property
    def provider_type(self) -> str:
        return "openai"

    async def get_llm_models(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> list[dict[str, str]]:
        """获取LLM模型列表（通过API）。"""
        url = f"{self._normalize_url(base_url)}/models"
        headers = self._build_auth_header(api_key, headers)

        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return parse_model_list(response.json())
        except Exception as e:
            logger.error(f"Failed to fetch OpenAI LLM models: {e}")
            raise

    async def get_embedding_models(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> list[dict[str, str]]:
        """获取Embedding模型列表（预定义，OpenAI官方embedding模型）。"""
        return [
            {"id": "text-embedding-3-small", "name": "Text Embedding 3 Small"},
            {"id": "text-embedding-3-large", "name": "Text Embedding 3 Large"},
            {"id": "text-embedding-ada-002", "name": "Text Embedding Ada 002"},
        ]

    def supports_rerank(self) -> bool:
        return True
