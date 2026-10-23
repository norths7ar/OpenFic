"""OCX presentation pairing; raw upstream IDs remain the routing authority."""

from typing import Any

from app.models.clients.provider_discovery import DiscoverySnapshot
from app.models.clients.reasoning_capabilities import get_reasoning_capability


def speed_variants(model_id: str, provider: Any, snapshot: DiscoverySnapshot) -> dict[str, str]:
    variants = {"standard": model_id}
    if (
        getattr(provider, "catalog_mode", "generic") == "ocx"
        and snapshot.checked_at is not None
        and model_id in snapshot.models
        and model_id + "--fast" in snapshot.models
    ):
        variants["fast"] = model_id + "--fast"
    return variants


def model_speed_fields(
    model_id: str,
    provider: Any,
    snapshot: DiscoverySnapshot,
    api_key: str = "",
    custom_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    variants = speed_variants(model_id, provider, snapshot)
    capabilities = {}
    for speed, raw_id in variants.items():
        capability = get_reasoning_capability(
            provider.provider_type,
            raw_id,
            provider.url,
            api_key=api_key,
            custom_headers=custom_headers,
        )
        capabilities[speed] = {
            "levels": list(capability.levels or ()),
            "status": capability.status,
            "default": capability.default,
        }
    return {"speed_variants": variants, "speed_reasoning_capabilities": capabilities}


def visible_directory(
    provider: Any,
    snapshot: DiscoverySnapshot,
    api_key: str,
    headers: dict[str, str],
) -> list[dict[str, Any]]:
    result = []
    for raw_id, model in snapshot.models.items():
        if (
            getattr(provider, "catalog_mode", "generic") == "ocx"
            and raw_id.endswith("--fast")
            and snapshot.checked_at is not None
            and raw_id.removesuffix("--fast") in snapshot.models
        ):
            continue
        result.append({**model, **model_speed_fields(raw_id, provider, snapshot, api_key, headers)})
    return result
