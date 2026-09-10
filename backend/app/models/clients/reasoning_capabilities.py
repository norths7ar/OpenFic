"""Confirmed effort controls for a provider/model/endpoint, shared by API and runtime."""

import re
import time
from typing import Any, cast
from urllib.parse import urlparse

import httpx

from app.core.errors import ValidationError
from app.models.clients.model_params import REASONING_EFFORT_VALUES, ReasoningEffort

# Metadata is connection-scoped and short lived; never persist provider secrets.
_advertised: dict[str, tuple[float, dict[str, tuple[ReasoningEffort, ...]]]] = {}


def remember_advertised_efforts(base_url: str, models: list[dict[str, Any]]) -> None:
    levels_by_model = {}
    for model in models:
        if not isinstance(model, dict):
            continue
        values = model.get("reasoning_efforts")
        if isinstance(values, list):
            values = [value.get("value") if isinstance(value, dict) else value for value in values]
        elif isinstance(model.get("capabilities"), dict):
            values = model["capabilities"].get("reasoning_effort")
        if isinstance(values, list) and isinstance(model.get("id"), str):
            levels_by_model[model["id"]] = tuple(
                dict.fromkeys(
                    cast(ReasoningEffort, value)
                    for value in values
                    if isinstance(value, str)
                    and value in REASONING_EFFORT_VALUES
                    and value != "off"
                )
            )
    _advertised[base_url.rstrip("/")] = (time.monotonic(), levels_by_model)


async def refresh_advertised_efforts(
    provider_type: str, base_url: str, api_key: str, custom_headers: dict[str, str] | None = None
) -> None:
    if provider_type not in {"openai-compatible", "openai-compatible-responses"} or not base_url:
        return
    cached = _advertised.get(base_url.rstrip("/"))
    if cached is not None and time.monotonic() - cached[0] < 300:
        return
    from app.models.adapters.openai_compatible import OpenAICompatibleAdapter

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await OpenAICompatibleAdapter().get_llm_models(
                client, base_url, api_key, headers=custom_headers
            )
    except (httpx.HTTPError, ValueError):
        pass
    if base_url.rstrip("/") not in _advertised or cached is _advertised.get(base_url.rstrip("/")):
        # Failed discovery does not invalidate an already running connection.
        _advertised[base_url.rstrip("/")] = (time.monotonic(), cached[1] if cached else {})


def _official(base_url: str, hostname: str) -> bool:
    return not base_url or urlparse(base_url).hostname == hostname


def supported_reasoning_efforts(
    provider_type: str, model_id: str, base_url: str = ""
) -> tuple[ReasoningEffort, ...]:
    """Unknown compatible endpoints do not inherit capabilities from a model name."""
    if provider_type in {"openai-compatible", "openai-compatible-responses"}:
        cached = _advertised.get(base_url.rstrip("/"))
        if cached is not None:
            advertised = cached[1].get(model_id)
            if advertised is not None:
                return advertised
    name = model_id.lower()
    if provider_type in {
        "openai",
        "openai-compatible",
        "openai-compatible-responses",
    } and _official(base_url, "api.openai.com"):
        name = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", name)
        if name == "gpt-5":
            return ("minimal", "low", "medium", "high")
        if name == "gpt-5.1":
            return ("none", "low", "medium", "high")
        if name in {"gpt-5.2", "gpt-5.4"}:
            return ("none", "low", "medium", "high", "xhigh")
        if name == "gpt-5.6-sol":
            return ("none", "low", "medium", "high", "xhigh", "max")
    if provider_type in {"anthropic", "anthropic-compatible"} and _official(
        base_url, "api.anthropic.com"
    ):
        name = re.sub(r"-\d{8}$", "", name)
        if name in {"claude-opus-4-6", "claude-sonnet-4-6"}:
            return ("low", "medium", "high", "max")
        if name in {"claude-opus-4-7", "claude-opus-4-8", "claude-opus-5", "claude-sonnet-5"}:
            return ("low", "medium", "high", "xhigh", "max")
    if provider_type == "google-genai" and _official(base_url, "generativelanguage.googleapis.com"):
        if name in {"gemini-3.1-pro-preview", "gemini-3.8-flash", "gemini-3.7-flash"}:
            return ("low", "medium", "high")
        if name in {
            "gemini-3-flash-preview",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash-lite",
        }:
            return ("minimal", "low", "medium", "high")
        if name == "gemini-3.1-flash-lite-image":
            return ("minimal", "high")
    return ()


def resolve_reasoning_effort(
    provider_type: str, model_id: str, base_url: str, effort: str | None
) -> ReasoningEffort | None:
    # Legacy off means unspecified, not a promise to disable the model's thinking.
    if effort is None or effort == "off":
        return None
    levels = supported_reasoning_efforts(provider_type, model_id, base_url)
    if effort not in levels:
        raise ValidationError(f"当前模型连接不支持推理档位 {effort}，请使用默认值或可用档位")
    return cast(ReasoningEffort, effort)
