import pytest

from app.core.errors import ValidationError
from app.models.clients.model_factory import ModelConfig, create_chat_model
from app.models.clients.reasoning_capabilities import (
    resolve_reasoning_effort,
    supported_reasoning_efforts,
)


@pytest.mark.parametrize(
    "model,levels",
    [
        ("gpt-5", ("minimal", "low", "medium", "high")),
        ("gpt-5.1-2025-11-13", ("none", "low", "medium", "high")),
        ("gpt-5.6-sol", ("none", "low", "medium", "high", "xhigh", "max")),
        ("gpt-5-fake", ()),
        ("unknown", ()),
    ],
)
def test_openai_exact_model_efforts(model, levels):
    assert supported_reasoning_efforts("openai", model, "https://api.openai.com/v1") == levels


def test_proxy_does_not_inherit_model_capabilities():
    assert (
        supported_reasoning_efforts("openai-compatible", "gpt-5", "http://localhost:4000/v1") == ()
    )
    assert (
        resolve_reasoning_effort("openai-compatible", "gpt-5", "http://localhost:4000/v1", "off")
        is None
    )
    with pytest.raises(ValidationError):
        resolve_reasoning_effort("openai-compatible", "gpt-5", "http://localhost:4000/v1", "high")


@pytest.mark.parametrize("effort,expected", [("none", "none"), ("high", "high"), ("off", None)])
def test_openai_wire_effort_is_not_reinterpreted(effort, expected):
    model = create_chat_model(
        ModelConfig(
            provider_type="openai",
            base_url="https://api.openai.com/v1",
            api_key="test",
            model_id="gpt-5.1",
            reasoning_effort=effort,
        )
    )
    assert model._get_request_payload("hello").get("reasoning_effort") == expected


def test_no_silent_effort_downgrade():
    with pytest.raises(ValidationError):
        resolve_reasoning_effort("openai", "gpt-5", "", "max")


@pytest.mark.asyncio
async def test_compatible_advertised_levels_are_cached_and_used_on_wire():
    import httpx
    import respx

    from app.models.clients.reasoning_capabilities import _advertised, refresh_advertised_efforts

    url = "http://local-reasoning.test:10100/v1"
    _advertised.pop(url, None)
    with respx.mock as mock:
        route = mock.get(url + "/models").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "gpt-5.5",
                            "reasoning_efforts": [{"value": "low"}, {"value": "xhigh"}],
                        }
                    ]
                },
            )
        )
        await refresh_advertised_efforts("openai-compatible-responses", url, "")
        await refresh_advertised_efforts("openai-compatible-responses", url, "")
        assert route.call_count == 1
    assert supported_reasoning_efforts("openai-compatible-responses", "gpt-5.5", url) == (
        "low",
        "xhigh",
    )
    model = create_chat_model(
        ModelConfig(
            provider_type="openai-compatible-responses",
            base_url=url,
            api_key="test",
            model_id="gpt-5.5",
            reasoning_effort="xhigh",
        )
    )
    assert model._get_request_payload("hello")["reasoning"]["effort"] == "xhigh"
    _advertised.pop(url, None)


@pytest.mark.parametrize(
    "model,expected",
    [
        ("gemini-3.1-pro-preview", ("low", "medium", "high")),
        ("gemini-3-flash-preview", ("minimal", "low", "medium", "high")),
        ("gemini-2.5-pro", ()),
    ],
)
def test_google_thinking_levels_are_model_specific(model, expected):
    assert supported_reasoning_efforts("google-genai", model) == expected


@pytest.mark.asyncio
async def test_cache_age_does_not_break_active_run_and_failure_retains_last_known():
    import httpx
    import respx

    from app.models.clients.reasoning_capabilities import _advertised, refresh_advertised_efforts

    url = "http://reasoning-expiry.test/v1"
    _advertised[url] = (0, {"model": ("high",)})
    assert resolve_reasoning_effort("openai-compatible", "model", url, "high") == "high"
    with respx.mock as mock:
        mock.get(url + "/models").mock(return_value=httpx.Response(502))
        await refresh_advertised_efforts("openai-compatible", url, "")
    assert resolve_reasoning_effort("openai-compatible", "model", url, "high") == "high"
    _advertised[url] = (0, _advertised[url][1])
    with respx.mock as mock:
        mock.get(url + "/models").mock(return_value=httpx.Response(200, json={"data": []}))
        await refresh_advertised_efforts("openai-compatible", url, "")
    assert supported_reasoning_efforts("openai-compatible", "model", url) == ()
    _advertised.pop(url)
