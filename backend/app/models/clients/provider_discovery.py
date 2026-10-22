"""Shared, connection-scoped LLM directory and last-good capability snapshot."""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import httpx

DiscoveryStatus = Literal["ok", "error", "unsupported", "unknown"]
UpstreamStatus = Literal["listed", "not_listed", "unknown"]
ConnectionKey = tuple[str, str, str]
TTL_SECONDS = 300
RETRY_SECONDS = 30


@dataclass(frozen=True)
class DiscoverySnapshot:
    status: DiscoveryStatus = "unknown"
    # On failure these remain the last successful directory, for capability resolution only.
    models: dict[str, dict[str, Any]] = field(default_factory=dict)
    checked_at: str | None = None
    retry_at: float = 0
    error: str | None = None

    def upstream_status(self, model_id: str) -> UpstreamStatus:
        if self.status != "ok" or time.monotonic() >= self.retry_at:
            return "unknown"
        return "listed" if model_id in self.models else "not_listed"


_snapshots: dict[ConnectionKey, DiscoverySnapshot] = {}
_inflight: dict[ConnectionKey, asyncio.Task[DiscoverySnapshot]] = {}


def _connection_key(
    provider_type: str, base_url: str, api_key: str, custom_headers: dict[str, str] | None
) -> ConnectionKey:
    credentials = json.dumps([api_key, custom_headers or {}], sort_keys=True).encode()
    return provider_type, base_url.rstrip("/"), hashlib.sha256(credentials).hexdigest()


def get_discovery_snapshot(
    provider_type: str,
    base_url: str,
    api_key: str = "",
    custom_headers: dict[str, str] | None = None,
) -> DiscoverySnapshot:
    return _snapshots.get(
        _connection_key(provider_type, base_url, api_key, custom_headers), DiscoverySnapshot()
    )


async def _fetch_directory(
    key: ConnectionKey,
    provider_type: str,
    base_url: str,
    api_key: str,
    custom_headers: dict[str, str] | None,
) -> DiscoverySnapshot:
    from app.models.adapters.model_list import normalize_model_list
    from app.models.registry import AdapterRegistry

    previous = _snapshots.get(key, DiscoverySnapshot())
    try:
        adapter = AdapterRegistry.get_adapter(provider_type)
        if adapter.llm_models_are_static or not adapter.supports_llm():
            models = []
            if adapter.llm_models_are_static:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    models = normalize_model_list(
                        await adapter.get_llm_models(
                            client, base_url, api_key, headers=custom_headers
                        )
                    )
            snapshot = DiscoverySnapshot(
                status="unsupported",
                models={model["id"]: model for model in models},
                retry_at=time.monotonic() + TTL_SECONDS,
            )
        else:
            async with httpx.AsyncClient(timeout=5.0) as client:
                models = await adapter.discover_llm_models(
                    client, base_url, api_key, headers=custom_headers
                )
            models = normalize_model_list(models)
            snapshot = DiscoverySnapshot(
                status="ok",
                models={model["id"]: model for model in models},
                checked_at=datetime.now(UTC).isoformat(),
                retry_at=time.monotonic() + TTL_SECONDS,
            )
    except Exception as exc:
        snapshot = DiscoverySnapshot(
            status="error",
            models=previous.models,
            checked_at=previous.checked_at,
            retry_at=time.monotonic() + RETRY_SECONDS,
            error=str(exc),
        )
    _snapshots[key] = snapshot
    return snapshot


async def discover_provider_models(
    provider_type: str,
    base_url: str,
    api_key: str = "",
    custom_headers: dict[str, str] | None = None,
    *,
    refresh: bool = False,
) -> DiscoverySnapshot:
    """Refresh on expiry (or explicitly); concurrent callers share one upstream request."""
    key = _connection_key(provider_type, base_url, api_key, custom_headers)
    task = _inflight.get(key)
    if task is None:
        cached = _snapshots.get(key)
        if not refresh and cached is not None and time.monotonic() < cached.retry_at:
            return cached
        task = asyncio.create_task(
            _fetch_directory(key, provider_type, base_url, api_key, custom_headers)
        )
        _inflight[key] = task
        task.add_done_callback(lambda _: _inflight.pop(key, None))
    # A cancelled HTTP request must not cancel discovery for the other callers.
    return await asyncio.shield(task)
