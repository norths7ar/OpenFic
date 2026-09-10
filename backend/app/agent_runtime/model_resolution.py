"""Resolve persisted model records into agent runtime configuration."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import EncryptionService
from app.core.errors import NotFoundError
from app.models.clients.reasoning_capabilities import (
    refresh_advertised_efforts,
    resolve_reasoning_effort,
)
from app.models.repos import model_provider_repo, model_repo
from app.models.services.model_provider_service import ModelProviderService
from app.settings import settings


async def build_model_config(
    model: Any,
    provider: Any,
    api_key: str,
    reasoning_effort: str | None = None,
    custom_headers: dict[str, str] | None = None,
) -> dict:
    model_config = {
        "model_record_id": model.id,
        "provider_type": provider.provider_type,
        "base_url": provider.url,
        "api_key": api_key,
        "model_id": model.model_id,
        "max_context_tokens": model.context_length,
        "input_price": getattr(model, "input_price", 0.0),
        "output_price": getattr(model, "output_price", 0.0),
        "cache_read_price": getattr(model, "cache_read_price", 0.0),
        "cache_write_price": getattr(model, "cache_write_price", 0.0),
        "temperature": model.temperature,
        "top_p": model.top_p,
        "top_k": model.top_k,
        "min_p": model.min_p,
        "top_a": model.top_a,
        "max_tokens": model.max_tokens,
        "frequency_penalty": model.frequency_penalty,
        "presence_penalty": model.presence_penalty,
        "repetition_penalty": model.repetition_penalty,
    }
    await refresh_advertised_efforts(provider.provider_type, provider.url, api_key, custom_headers)
    resolved_effort = resolve_reasoning_effort(
        provider.provider_type, model.model_id, provider.url, reasoning_effort
    )
    if resolved_effort is not None:
        model_config["reasoning_effort"] = resolved_effort
    if custom_headers:
        model_config["custom_headers"] = custom_headers
    return model_config


async def resolve_model_config(
    session: AsyncSession,
    model_id: str,
    reasoning_effort: str | None = None,
) -> dict:
    model = await model_repo.get_by_id(session, model_id)
    if model is None:
        raise NotFoundError(f"模型不存在：{model_id}")

    provider = await model_provider_repo.get_by_id(session, model.provider_id)
    if provider is None:
        raise NotFoundError(f"模型提供商不存在：{model.provider_id}")

    encryption_service = EncryptionService(settings.encryption_key)
    if not provider.api_key_encrypted or not provider.api_key_encrypted.strip():
        api_key = ""
    else:
        try:
            api_key = encryption_service.decrypt(provider.api_key_encrypted)
        except Exception as exc:
            raise ValueError("API密钥解密失败") from exc

    custom_headers = ModelProviderService(encryption_service).get_decrypted_custom_headers(provider)
    return await build_model_config(
        model,
        provider,
        api_key,
        reasoning_effort,
        custom_headers,
    )


async def resolve_legacy_model_config(
    session: AsyncSession,
    legacy_model_config: dict[str, object],
) -> dict:
    model_id = legacy_model_config.get("model_id")
    provider_type = legacy_model_config.get("provider_type")
    base_url = legacy_model_config.get("base_url")
    if (
        not isinstance(model_id, str)
        or not model_id
        or not isinstance(provider_type, str)
        or not provider_type
        or not isinstance(base_url, str)
        or not base_url
    ):
        raise NotFoundError("会话模型配置无法恢复")

    model = await model_repo.get_by_legacy_agent_config(
        session,
        model_id=model_id,
        provider_type=provider_type,
        base_url=base_url,
    )
    if model is None:
        raise NotFoundError("会话模型配置无法恢复")
    return await resolve_model_config(session, model.id)
