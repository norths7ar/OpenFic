from importlib.util import find_spec

import httpx
import pytest
import respx
import tiktoken.load
import tiktoken.registry

from app.agent_runtime.model_config import to_client_model_config, without_api_key
from app.models.clients.model_factory import ModelConfig, create_chat_model


def requires_extra(module: str):
    return pytest.mark.skipif(
        find_spec(module) is None, reason=f"optional provider SDK missing: {module}"
    )


def test_to_client_model_config_excludes_internal_model_record_id():
    config = to_client_model_config(
        {
            "model_record_id": "model-record-1",
            "provider_type": "openai-compatible",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test",
            "model_id": "gpt-4o",
        }
    )

    model = create_chat_model(ModelConfig(**config))

    assert model.model_name == "gpt-4o"


def test_without_api_key_removes_custom_headers_from_persisted_config():
    persisted = without_api_key(
        {
            "api_key": "sk-test",
            "custom_headers": {"X-Provider-Token": "custom-token"},
        }
    )

    assert persisted == {}


def test_create_chat_model_openai_returns_chat_openai():
    config = ModelConfig(
        provider_type="openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        model_id="gpt-4o",
    )
    model = create_chat_model(config)

    from langchain_openai import ChatOpenAI

    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "gpt-4o"
    assert model.stream_chunk_timeout == 120.0
    assert model.request_timeout == (10.0, 600.0)


@requires_extra("langchain_anthropic")
def test_create_chat_model_anthropic_uses_native_client():
    config = ModelConfig(
        provider_type="anthropic",
        base_url="",
        api_key="sk-ant-test",
        model_id="claude-sonnet-4-6",
    )
    model = create_chat_model(config)

    from langchain_anthropic import ChatAnthropic

    assert isinstance(model, ChatAnthropic)


@requires_extra("langchain_anthropic")
def test_create_chat_model_anthropic_compatible_uses_anthropic_client_with_custom_url():
    config = ModelConfig(
        provider_type="anthropic-compatible",
        base_url="https://gateway.example/v1",
        api_key="test-key",
        model_id="custom-claude",
        reasoning_effort="off",
    )

    model = create_chat_model(config)

    from langchain_anthropic import ChatAnthropic

    assert isinstance(model, ChatAnthropic)
    assert model.anthropic_api_url == "https://gateway.example/v1"
    assert model.effort is None
    assert model.max_retries == 0


@requires_extra("langchain_anthropic")
def test_create_chat_model_custom_providers_send_custom_headers():
    openai_model = create_chat_model(
        ModelConfig(
            provider_type="openai-compatible",
            base_url="https://gateway.example/v1",
            api_key="test-key",
            model_id="custom-model",
            custom_headers={"X-Provider-Token": "custom-token"},
        )
    )
    anthropic_model = create_chat_model(
        ModelConfig(
            provider_type="anthropic-compatible",
            base_url="https://gateway.example/v1",
            api_key="test-key",
            model_id="custom-claude",
            custom_headers={"X-Provider-Token": "custom-token"},
        )
    )

    assert openai_model.default_headers["X-Provider-Token"] == "custom-token"
    assert anthropic_model.default_headers["X-Provider-Token"] == "custom-token"


def test_create_chat_model_with_temperature():
    config = ModelConfig(
        provider_type="openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        model_id="gpt-4o",
        temperature=0.7,
    )
    model = create_chat_model(config)
    assert model.temperature == 0.7


def test_create_chat_model_omits_default_advanced_params_from_request():
    model = create_chat_model(
        ModelConfig(
            provider_type="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            model_id="gpt-4o",
            temperature=1.0,
            top_p=1.0,
            top_k=0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            repetition_penalty=1.0,
            min_p=0.0,
            top_a=0.0,
        )
    )

    assert model._default_params == {  # type: ignore[attr-defined]
        "model": "gpt-4o",
        "stream": False,
    }


def test_create_chat_model_sends_non_default_advanced_params():
    model = create_chat_model(
        ModelConfig(
            provider_type="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            model_id="gpt-4o",
            temperature=0.7,
            top_p=0.9,
            top_k=32,
            frequency_penalty=0.2,
            presence_penalty=0.1,
            repetition_penalty=1.1,
            min_p=0.05,
            top_a=0.1,
        )
    )

    assert model._default_params == {  # type: ignore[attr-defined]
        "model": "gpt-4o",
        "stream": False,
        "temperature": 0.7,
        "top_p": 0.9,
        "frequency_penalty": 0.2,
        "presence_penalty": 0.1,
        "extra_body": {
            "top_k": 32,
            "repetition_penalty": 1.1,
            "min_p": 0.05,
            "top_a": 0.1,
        },
    }


def test_create_chat_model_omits_disabled_reasoning_effort():
    model = create_chat_model(
        ModelConfig(
            provider_type="openai-compatible",
            base_url="https://custom.api/v1",
            api_key="sk-test",
            model_id="new-reasoning-model",
            reasoning_effort="off",
        )
    )

    assert model._default_params == {  # type: ignore[attr-defined]
        "model": "new-reasoning-model",
        "stream": False,
    }


@requires_extra("langchain_deepseek")
def test_create_chat_model_deepseek_omits_disabled_reasoning_effort():
    model = create_chat_model(
        ModelConfig(
            provider_type="deepseek",
            base_url="https://api.deepseek.com",
            api_key="sk-test",
            model_id="deepseek-reasoner",
            reasoning_effort="off",
        )
    )

    assert "reasoning_effort" not in model._default_params  # type: ignore[attr-defined]


@requires_extra("langchain_anthropic")
def test_create_chat_model_maps_anthropic_reasoning_effort():
    model = create_chat_model(
        ModelConfig(
            provider_type="anthropic",
            base_url="",
            api_key="sk-ant-test",
            model_id="claude-sonnet-4-6",
            reasoning_effort="high",
        )
    )

    assert model.effort == "high"


@pytest.mark.parametrize(
    "provider,model,url",
    [
        ("openai-compatible", "gpt-5", "http://localhost:8080/v1"),
        ("groq", "openai/gpt-oss-120b", "https://api.groq.com/openai/v1"),
        ("cohere", "command-a-reasoning-08-2025", "https://api.cohere.com/v2"),
        ("mistral", "magistral-medium", "https://api.mistral.ai"),
        (
            "nvidia-ai-endpoints",
            "deepseek-ai/deepseek-v4-pro",
            "https://integrate.api.nvidia.com/v1",
        ),
    ],
)
def test_unknown_connection_rejects_unverified_effort(provider, model, url):
    from app.core.errors import ValidationError

    with pytest.raises(ValidationError, match="不支持推理档位"):
        create_chat_model(
            ModelConfig(
                provider_type=provider,
                base_url=url,
                api_key="test",
                model_id=model,
                reasoning_effort="max",
            )
        )


@requires_extra("langchain_anthropic")
def test_create_chat_model_disables_provider_internal_retries_for_anthropic():
    config = ModelConfig(
        provider_type="anthropic",
        base_url="",
        api_key="sk-ant-test",
        model_id="claude-sonnet-4-6",
    )
    model = create_chat_model(config)
    assert model.max_retries == 0


@requires_extra("langchain_deepseek")
def test_create_chat_model_disables_provider_internal_retries_for_deepseek():
    config = ModelConfig(
        provider_type="deepseek",
        base_url="https://api.deepseek.com",
        api_key="sk-test",
        model_id="deepseek-v4-flash",
    )
    model = create_chat_model(config)
    assert model.max_retries == 0


@requires_extra("langchain_mistralai")
def test_create_chat_model_disables_provider_internal_retries_for_mistral():
    config = ModelConfig(
        provider_type="mistral",
        base_url="https://api.mistral.ai",
        api_key="sk-mistral-test",
        model_id="mistral-small",
    )
    model = create_chat_model(config)
    assert model.max_retries == 0


@requires_extra("langchain_google_genai")
def test_create_chat_model_configures_google_genai_retries():
    config = ModelConfig(
        provider_type="google-genai",
        base_url="",
        api_key="sk-google-test",
        model_id="gemini-2.0-flash",
    )
    model = create_chat_model(config)
    assert model.max_retries == 1


def test_create_chat_model_unknown_provider_falls_back_to_openai():
    config = ModelConfig(
        provider_type="some-unknown-provider",
        base_url="https://custom.api/v1",
        api_key="sk-test",
        model_id="custom-model",
    )
    model = create_chat_model(config)

    from langchain_openai import ChatOpenAI

    assert isinstance(model, ChatOpenAI)


@requires_extra("langchain_anthropic")
def test_create_chat_model_uses_native_client_for_configured_provider():
    config = ModelConfig(
        provider_type="anthropic",
        base_url="https://api.anthropic.com",
        api_key="sk-ant-test",
        model_id="claude-sonnet-4-6",
    )

    model = create_chat_model(config)

    from langchain_anthropic import ChatAnthropic

    assert isinstance(model, ChatAnthropic)
    assert model.anthropic_api_url == "https://api.anthropic.com"


@requires_extra("langchain_deepseek")
def test_create_chat_model_deepseek_uses_native_client(monkeypatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "llm_chunk_timeout", 77.0)
    config = ModelConfig(
        provider_type="deepseek",
        base_url="https://api.deepseek.com",
        api_key="sk-test",
        model_id="deepseek-v4-flash",
    )
    model = create_chat_model(config)
    from langchain_deepseek import ChatDeepSeek

    assert isinstance(model, ChatDeepSeek)
    assert model.stream_chunk_timeout == 77.0


@requires_extra("langchain_openrouter")
def test_create_chat_model_openrouter_uses_native_client(monkeypatch):
    from app.settings import settings

    monkeypatch.setattr(settings, "llm_request_timeout", 600.0)
    config = ModelConfig(
        provider_type="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-or-test",
        model_id="openai/gpt-4o-mini",
    )

    model = create_chat_model(config)

    from langchain_openrouter import ChatOpenRouter

    assert isinstance(model, ChatOpenRouter)
    assert model.request_timeout == 600000


@requires_extra("langchain_groq")
def test_create_chat_model_groq_uses_native_client():
    config = ModelConfig(
        provider_type="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key="gsk_test",
        model_id="llama-3.3-70b-versatile",
    )

    model = create_chat_model(config)

    from langchain_groq import ChatGroq

    assert isinstance(model, ChatGroq)


@requires_extra("langchain_cohere")
def test_create_chat_model_cohere_uses_native_client():
    config = ModelConfig(
        provider_type="cohere",
        base_url="https://api.cohere.com/v2",
        api_key="cohere-test",
        model_id="command-a-03-2025",
    )

    model = create_chat_model(config)

    from langchain_cohere import ChatCohere

    assert isinstance(model, ChatCohere)


def test_create_chat_model_ollama_uses_openai_compatible_client():
    config = ModelConfig(
        provider_type="ollama",
        base_url="https://ollama.com/v1",
        api_key="ollama-test",
        model_id="glm-5",
    )

    model = create_chat_model(config)

    from langchain_openai import ChatOpenAI

    assert isinstance(model, ChatOpenAI)
    assert str(model.root_client.base_url) == "https://ollama.com/v1/"


@requires_extra("langchain_amazon_nova")
def test_create_chat_model_amazon_nova_uses_native_client():
    config = ModelConfig(
        provider_type="amazon-nova",
        base_url="https://api.nova.amazon.com/v1",
        api_key="nova-test",
        model_id="nova-2-pro-v1",
    )

    model = create_chat_model(config)

    from langchain_amazon_nova import ChatAmazonNova

    assert isinstance(model, ChatAmazonNova)


def test_create_chat_model_openai_compatible_enables_stream_usage_for_custom_base_url():
    config = ModelConfig(
        provider_type="openai-compatible",
        base_url="https://custom.api/v1",
        api_key="sk-test",
        model_id="custom-model",
    )
    model = create_chat_model(config)

    from langchain_openai import ChatOpenAI

    assert isinstance(model, ChatOpenAI)
    assert model.stream_usage is True


@respx.mock
def test_create_chat_model_anonymous_compatible_sync_request_omits_authorization() -> None:
    route = respx.get("http://127.0.0.1:10100/v1/models").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    model = create_chat_model(
        ModelConfig(
            provider_type="openai-compatible",
            base_url="http://127.0.0.1:10100/v1",
            api_key="",
            model_id="proxy/model",
        )
    )

    list(model.root_client.models.list())

    assert route.called
    assert "authorization" not in route.calls[0].request.headers


@pytest.mark.asyncio
@respx.mock
async def test_create_chat_model_anonymous_compatible_async_request_omits_authorization() -> None:
    route = respx.get("http://127.0.0.1:10100/v1/models").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    model = create_chat_model(
        ModelConfig(
            provider_type="openai-compatible",
            base_url="http://127.0.0.1:10100/v1",
            api_key="",
            model_id="proxy/model",
        )
    )

    await model.root_async_client.models.list()

    assert route.called
    assert "authorization" not in route.calls[0].request.headers


@pytest.mark.asyncio
@respx.mock
async def test_create_chat_model_anonymous_chat_completions_request_omits_authorization() -> None:
    route = respx.post("http://127.0.0.1:10100/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "proxy/model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "OK"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )
    )
    model = create_chat_model(
        ModelConfig(
            provider_type="openai-compatible",
            base_url="http://127.0.0.1:10100/v1",
            api_key="",
            model_id="proxy/model",
        )
    )

    await model.root_async_client.chat.completions.create(
        model="proxy/model",
        messages=[{"role": "user", "content": "ping"}],
    )

    assert route.called
    assert "authorization" not in route.calls[0].request.headers


@pytest.mark.asyncio
@respx.mock
async def test_create_chat_model_anonymous_responses_request_omits_authorization() -> None:
    route = respx.post("http://127.0.0.1:10100/v1/responses").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "resp-test",
                "object": "response",
                "created_at": 0,
                "model": "proxy/model",
                "output": [],
            },
        )
    )
    model = create_chat_model(
        ModelConfig(
            provider_type="openai-compatible-responses",
            base_url="http://127.0.0.1:10100/v1",
            api_key="",
            model_id="proxy/model",
        )
    )

    await model.root_async_client.responses.create(model="proxy/model", input="ping")

    assert route.called
    assert "authorization" not in route.calls[0].request.headers


@respx.mock
def test_create_chat_model_anonymous_compatible_keeps_custom_authorization() -> None:
    route = respx.get("http://127.0.0.1:10100/v1/models").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    model = create_chat_model(
        ModelConfig(
            provider_type="openai-compatible",
            base_url="http://127.0.0.1:10100/v1",
            api_key="",
            model_id="proxy/model",
            custom_headers={"Authorization": "Token configured-by-user"},
        )
    )

    list(model.root_client.models.list())

    assert route.calls[0].request.headers["authorization"] == "Token configured-by-user"


def test_create_chat_model_openai_responses_compatible_uses_responses_api():
    config = ModelConfig(
        provider_type="openai-compatible-responses",
        base_url="https://gateway.example/v1",
        api_key="sk-test",
        model_id="responses-model",
    )
    model = create_chat_model(config)

    from langchain_openai import ChatOpenAI

    assert isinstance(model, ChatOpenAI)
    assert model.use_responses_api is True
    assert str(model.root_client.base_url) == "https://gateway.example/v1/"


@requires_extra("langchain_deepseek")
def test_create_chat_model_deepseek_enables_stream_usage():
    config = ModelConfig(
        provider_type="deepseek",
        base_url="https://api.deepseek.com",
        api_key="sk-test",
        model_id="deepseek-v4-flash",
    )
    model = create_chat_model(config)

    from langchain_deepseek import ChatDeepSeek

    assert isinstance(model, ChatDeepSeek)
    assert model.stream_usage is True


@requires_extra("langchain_deepseek")
def test_create_chat_model_deepseek_uses_bundled_tiktoken_encoding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path / "tiktoken-cache"))
    monkeypatch.setattr(tiktoken.registry, "ENCODINGS", {})

    def fail_if_network_requested(_: str) -> bytes:
        raise AssertionError("LangChain token counting must not request network resources")

    monkeypatch.setattr(tiktoken.load, "read_file", fail_if_network_requested)
    model = create_chat_model(
        ModelConfig(
            provider_type="deepseek",
            base_url="https://api.deepseek.com",
            api_key="sk-test",
            model_id="deepseek-chat",
        )
    )

    assert model.get_token_ids("OpenFic 离线 token 测试")
