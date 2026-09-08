"""Read-only validation calls for saved model configurations."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

import httpx

from app.core.encryption import EncryptionService
from app.core.errors import ProviderAuthError, ProviderTimeoutError
from app.models.clients.embedding_client import EmbeddingClient, EmbeddingConfig
from app.models.clients.llm_client import LLMClient, LLMConfig
from app.models.clients.rerank_client import RerankClient, RerankConfig
from app.models.entities.model import Model
from app.models.entities.model_provider import ModelProvider
from app.models.registry import AdapterRegistry
from app.models.services.model_provider_service import ModelProviderService

ValidationErrorCode = Literal[
    "authentication_failed",
    "connection_failed",
    "model_not_found",
    "protocol_incompatible",
    "capability_incompatible",
    "rate_limited",
    "timed_out",
    "unknown_error",
]


@dataclass(frozen=True)
class ModelValidationResult:
    success: bool
    message: str
    error_code: ValidationErrorCode | None = None
    detail: str | None = None


class ModelValidationService:
    """Run the smallest useful request without changing saved model state."""

    def __init__(self, encryption_service: EncryptionService):
        self.encryption_service = encryption_service
        self.provider_service = ModelProviderService(encryption_service)

    async def validate(self, model: Model, provider: ModelProvider) -> ModelValidationResult:
        if not self._supports_task_type(provider, model.task_type):
            return self._failure(
                "capability_incompatible",
                "该提供商不支持此模型的任务类型，无法验证。",
            )

        install_hint = AdapterRegistry.unavailable_reason(provider.provider_type, model.task_type)
        if install_hint:
            return self._failure(
                "capability_incompatible",
                f"此提供商的 {model.task_type} 适配未安装，请运行 {install_hint}。",
            )

        api_key = self.provider_service.get_decrypted_api_key(provider)
        if (
            not provider.is_builtin
            and not api_key
            and provider.provider_type not in {"openai-compatible", "openai-compatible-responses"}
        ):
            return self._failure(
                "authentication_failed",
                "API Key 未配置或无法解密，请重新保存该提供商的凭据。",
            )

        try:
            custom_headers = self.provider_service.get_decrypted_custom_headers(provider)
            if model.task_type == "llm":
                await self._validate_llm(model, provider, api_key or "", custom_headers)
            elif model.task_type == "embedding":
                await self._validate_embedding(model, provider, api_key or "", custom_headers)
            elif model.task_type == "rerank":
                await self._validate_rerank(model, provider, api_key or "", custom_headers)
            else:
                return self._failure("capability_incompatible", "未知模型任务类型，无法验证。")
        except Exception as exc:  # Provider SDKs expose heterogeneous error classes.
            return self._classify_exception(exc)

        return ModelValidationResult(success=True, message="模型连接验证成功。")

    @staticmethod
    def _supports_task_type(provider: ModelProvider, task_type: str) -> bool:
        if provider.is_builtin:
            return task_type in {"embedding", "rerank"}
        return AdapterRegistry.is_supported(provider.provider_type, task_type)

    async def _validate_llm(
        self,
        model: Model,
        provider: ModelProvider,
        api_key: str,
        custom_headers: dict[str, str],
    ) -> None:
        client = LLMClient(
            LLMConfig(
                provider_type=provider.provider_type,
                base_url=provider.url,
                api_key=api_key,
                model_id=model.model_id,
                custom_headers=custom_headers or None,
                temperature=0,
                max_tokens=1,
                reasoning_effort="off",
                request_timeout=20,
            )
        )
        await client.generate([{"role": "user", "content": "Reply: OK"}], timeout=20)

    async def _validate_embedding(
        self,
        model: Model,
        provider: ModelProvider,
        api_key: str,
        custom_headers: dict[str, str],
    ) -> None:
        client = EmbeddingClient(
            EmbeddingConfig(
                provider_type=provider.provider_type,
                base_url=provider.url,
                api_key=api_key,
                model_id=model.model_id,
                custom_headers=custom_headers or None,
                dimensions=model.dimensions,
                batch_size=1,
            )
        )
        await asyncio.wait_for(client.embed_single("OpenFic"), timeout=20)

    async def _validate_rerank(
        self,
        model: Model,
        provider: ModelProvider,
        api_key: str,
        custom_headers: dict[str, str],
    ) -> None:
        client = RerankClient(
            RerankConfig(
                provider_type=provider.provider_type,
                base_url=provider.url,
                api_key=api_key,
                model_id=model.model_id,
                custom_headers=custom_headers or None,
                request_timeout=20,
            )
        )
        await client.rerank("OpenFic", ["connection test"], top_n=1)

    @staticmethod
    def _failure(
        error_code: ValidationErrorCode, message: str, detail: str | None = None
    ) -> ModelValidationResult:
        return ModelValidationResult(
            success=False, message=message, error_code=error_code, detail=detail
        )

    def _classify_exception(self, exc: Exception) -> ModelValidationResult:
        status_code = getattr(exc, "status_code", None)
        detail = self._safe_detail(exc)
        message = detail.lower()

        if isinstance(exc, (asyncio.TimeoutError, ProviderTimeoutError)):
            return self._failure("timed_out", "验证请求超时。", detail)
        if isinstance(exc, ProviderAuthError) or status_code in {401, 403}:
            return self._failure(
                "authentication_failed", "认证失败，请检查 API Key 或权限。", detail
            )
        if status_code == 429:
            return self._failure("rate_limited", "提供商限流，请稍后重试。", detail)
        if status_code == 404 or any(
            phrase in message
            for phrase in (
                "model not found",
                "model_not_found",
                "does not exist",
                "unknown model",
            )
        ):
            return self._failure("model_not_found", "提供商未找到该模型。", detail)
        if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
            return self._failure("connection_failed", "无法连接到提供商地址。", detail)
        if isinstance(exc, ValueError) and "unsupported" in message:
            return self._failure(
                "capability_incompatible", "提供商不支持该模型能力或任务类型。", detail
            )
        if status_code in {400, 405, 415, 422} or any(
            phrase in message
            for phrase in (
                "unsupported",
                "not support",
                "unknown parameter",
                "invalid request",
            )
        ):
            return self._failure(
                "protocol_incompatible",
                "提供商协议或模型能力与当前配置不兼容。",
                detail,
            )
        if isinstance(exc, httpx.HTTPError):
            return self._failure("connection_failed", "请求提供商时发生网络错误。", detail)
        return self._failure("unknown_error", "模型验证失败。", detail)

    @staticmethod
    def _safe_detail(exc: Exception) -> str:
        detail = str(exc).strip()
        return detail[:500] if detail else exc.__class__.__name__
