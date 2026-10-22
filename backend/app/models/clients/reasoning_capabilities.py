"""Reasoning controls advertised by each authenticated model connection."""

import hashlib
import json
import time
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import httpx

from app.core.errors import ValidationError
from app.models.clients.model_params import ReasoningEffort


@dataclass(frozen=True)
class ReasoningCapability:
    # None means unadvertised, while an explicit empty list means unsupported.
    levels: tuple[str, ...] | None = None
    default: str | None = None
    requests: dict[str, dict[str, Any]] | None = None

    @property
    def status(self) -> Literal["supported", "unsupported", "unknown"]:
        if self.levels is None:
            return "unknown"
        return "supported" if self.levels else "unsupported"


_advertised: dict[tuple[str, str, str], tuple[float, dict[str, ReasoningCapability]]] = {}


@lru_cache(maxsize=1)
def _default_profiles() -> list[dict[str, Any]]:
    with Path(__file__).with_name("reasoning_defaults.toml").open("rb") as source:
        return tomllib.load(source)["profiles"]


def _documented_capability(provider_type: str, model_id: str, base_url: str) -> ReasoningCapability:
    for profile in _default_profiles():
        if (
            provider_type in profile["provider_types"]
            and base_url.rstrip("/") in profile["base_urls"]
            and model_id in profile["models"]
        ):
            return ReasoningCapability(
                tuple(profile["levels"]), profile["default"], profile.get("requests")
            )
    return ReasoningCapability()


def _connection_key(
    provider_type: str, base_url: str, api_key: str, custom_headers: dict[str, str] | None
) -> tuple[str, str, str]:
    credentials = json.dumps([api_key, custom_headers or {}], sort_keys=True).encode()
    return provider_type, base_url.rstrip("/"), hashlib.sha256(credentials).hexdigest()


def parse_reasoning_capability(model: dict[str, Any]) -> ReasoningCapability:
    """Normalize advertised schemas, never infer controls from a model name."""
    values = model.get("reasoning_efforts")
    default = model.get("reasoning_effort")
    capabilities = model.get("capabilities")
    if not isinstance(values, list) and isinstance(capabilities, dict):
        values = capabilities.get("reasoning_effort")
    effort = model.get("effort")
    if not isinstance(values, list) and isinstance(effort, dict):
        values = effort.get("supported_levels")
        default = effort.get("default_level")
    if model.get("supports_reasoning_effort") is False:
        return ReasoningCapability(())
    if not isinstance(values, list):
        return ReasoningCapability()
    levels: list[str] = []
    for value in values:
        if isinstance(value, dict):
            if value.get("default") is True:
                default = value.get("value")
            value = value.get("value")
        # off is the application's legacy "use upstream default" sentinel.
        if isinstance(value, str) and value and value != "off" and value not in levels:
            levels.append(value)
    return ReasoningCapability(tuple(levels), default if default in levels else None)


def remember_advertised_efforts(
    base_url: str,
    models: list[dict[str, Any]],
    *,
    provider_type: str = "openai-compatible",
    api_key: str = "",
    custom_headers: dict[str, str] | None = None,
) -> None:
    models_by_id = {
        model["id"]: parse_reasoning_capability(model)
        for model in models
        if isinstance(model, dict) and isinstance(model.get("id"), str)
    }
    key = _connection_key(provider_type, base_url, api_key, custom_headers)
    _advertised[key] = (time.monotonic(), models_by_id)


async def refresh_advertised_efforts(
    provider_type: str, base_url: str, api_key: str, custom_headers: dict[str, str] | None = None
) -> None:
    if not base_url:
        return
    key = _connection_key(provider_type, base_url, api_key, custom_headers)
    cached = _advertised.get(key)
    if cached is not None and time.monotonic() - cached[0] < 300:
        return
    from app.models.registry import AdapterRegistry

    adapter = AdapterRegistry.get_adapter(provider_type)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            models = await adapter.get_llm_models(client, base_url, api_key, headers=custom_headers)
        remember_advertised_efforts(
            base_url,
            models,
            provider_type=provider_type,
            api_key=api_key,
            custom_headers=custom_headers,
        )
    except (httpx.HTTPError, ValueError):
        # Retry later; a temporary discovery failure must not erase known controls.
        _advertised[key] = (time.monotonic(), cached[1] if cached else {})


def get_reasoning_capability(
    provider_type: str,
    model_id: str,
    base_url: str = "",
    *,
    api_key: str = "",
    custom_headers: dict[str, str] | None = None,
) -> ReasoningCapability:
    cached = _advertised.get(_connection_key(provider_type, base_url, api_key, custom_headers))
    advertised = cached[1].get(model_id, ReasoningCapability()) if cached else ReasoningCapability()
    if advertised.levels is not None:
        return advertised
    return _documented_capability(provider_type, model_id, base_url)


def supported_reasoning_efforts(
    provider_type: str,
    model_id: str,
    base_url: str = "",
    *,
    api_key: str = "",
    custom_headers: dict[str, str] | None = None,
) -> tuple[ReasoningEffort, ...]:
    return (
        get_reasoning_capability(
            provider_type, model_id, base_url, api_key=api_key, custom_headers=custom_headers
        ).levels
        or ()
    )


def resolve_reasoning_effort(
    provider_type: str,
    model_id: str,
    base_url: str,
    effort: str | None,
    *,
    api_key: str = "",
    custom_headers: dict[str, str] | None = None,
) -> ReasoningEffort | None:
    if effort is None or effort == "off":
        return None
    capability = get_reasoning_capability(
        provider_type, model_id, base_url, api_key=api_key, custom_headers=custom_headers
    )
    if capability.levels is None:
        raise ValidationError("当前连接未声明此模型的推理档位，请使用默认值")
    if effort not in capability.levels:
        raise ValidationError(f"当前模型连接不支持推理档位 {effort}，请使用默认值或可用档位")
    return effort
