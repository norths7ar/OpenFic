"""Direct tests for agent runtime model resolution."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent_runtime import model_resolution
from app.core.errors import NotFoundError


def _model() -> SimpleNamespace:
    return SimpleNamespace(
        id="model-record",
        provider_id="provider-record",
        model_id="gpt-5",
        context_length=128000,
        temperature=1.0,
        top_p=1.0,
        top_k=0,
        min_p=0.0,
        top_a=0.0,
        max_tokens=None,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        repetition_penalty=1.0,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reasoning_effort", "expected"),
    [("off", None), ("high", "high")],
)
async def test_build_model_config_handles_reasoning_effort(
    reasoning_effort: str,
    expected: str | None,
) -> None:
    config = await model_resolution.build_model_config(
        _model(),
        SimpleNamespace(provider_type="openai", url="https://api.openai.com/v1"),
        "sk-test",
        reasoning_effort,
        {"X-Provider-Key": "header-secret"},
    )

    assert config["custom_headers"] == {"X-Provider-Key": "header-secret"}
    if expected is None:
        assert "reasoning_effort" not in config
    else:
        assert config["reasoning_effort"] == expected


@pytest.mark.asyncio
async def test_resolve_model_config_rejects_missing_model(monkeypatch) -> None:
    monkeypatch.setattr(model_resolution.model_repo, "get_by_id", AsyncMock(return_value=None))

    with pytest.raises(NotFoundError, match="模型不存在：missing-model"):
        await model_resolution.resolve_model_config(object(), "missing-model")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_resolve_model_config_rejects_missing_provider(monkeypatch) -> None:
    monkeypatch.setattr(model_resolution.model_repo, "get_by_id", AsyncMock(return_value=_model()))
    monkeypatch.setattr(
        model_resolution.model_provider_repo,
        "get_by_id",
        AsyncMock(return_value=None),
    )

    with pytest.raises(NotFoundError, match="模型提供商不存在：provider-record"):
        await model_resolution.resolve_model_config(object(), "model-record")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_resolve_model_config_includes_decrypted_custom_headers(monkeypatch) -> None:
    class FakeEncryptionService:
        def __init__(self, _key: str) -> None:
            pass

        def decrypt(self, _ciphertext: str) -> str:
            return "sk-test"

    class FakeModelProviderService:
        def __init__(self, _encryption_service: FakeEncryptionService) -> None:
            pass

        def get_decrypted_custom_headers(self, _provider: object) -> dict[str, str]:
            return {"X-Provider-Key": "header-secret"}

    monkeypatch.setattr(model_resolution.model_repo, "get_by_id", AsyncMock(return_value=_model()))
    monkeypatch.setattr(
        model_resolution.model_provider_repo,
        "get_by_id",
        AsyncMock(
            return_value=SimpleNamespace(
                api_key_encrypted="encrypted-key",
                provider_type="openai-compatible",
                url="https://api.example/v1",
            )
        ),
    )
    monkeypatch.setattr(model_resolution, "EncryptionService", FakeEncryptionService)
    monkeypatch.setattr(model_resolution, "ModelProviderService", FakeModelProviderService)

    config = await model_resolution.resolve_model_config(object(), "model-record")  # type: ignore[arg-type]

    assert config["custom_headers"] == {"X-Provider-Key": "header-secret"}


@pytest.mark.asyncio
async def test_resolve_model_config_wraps_api_key_decryption_failure(monkeypatch) -> None:
    class FailingEncryptionService:
        def __init__(self, _key: str) -> None:
            pass

        def decrypt(self, _ciphertext: str) -> str:
            raise RuntimeError("cannot decrypt")

    monkeypatch.setattr(model_resolution.model_repo, "get_by_id", AsyncMock(return_value=_model()))
    monkeypatch.setattr(
        model_resolution.model_provider_repo,
        "get_by_id",
        AsyncMock(
            return_value=SimpleNamespace(
                api_key_encrypted="bad-key",
                provider_type="openai-compatible",
                url="https://api.example/v1",
            )
        ),
    )
    monkeypatch.setattr(model_resolution, "EncryptionService", FailingEncryptionService)

    with pytest.raises(ValueError, match="API密钥解密失败"):
        await model_resolution.resolve_model_config(object(), "model-record")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_resolve_model_config_allows_empty_api_key_for_anonymous_provider(
    monkeypatch,
) -> None:
    class FailIfDecrypted:
        def __init__(self, _key: str) -> None:
            pass

        def decrypt(self, _ciphertext: str) -> str:
            raise AssertionError("empty API key must not be decrypted")

    monkeypatch.setattr(model_resolution.model_repo, "get_by_id", AsyncMock(return_value=_model()))
    monkeypatch.setattr(
        model_resolution.model_provider_repo,
        "get_by_id",
        AsyncMock(
            return_value=SimpleNamespace(
                api_key_encrypted="",
                custom_headers_encrypted="",
                provider_type="openai-compatible",
                url="http://127.0.0.1:10100/v1",
            )
        ),
    )
    monkeypatch.setattr(model_resolution, "EncryptionService", FailIfDecrypted)

    config = await model_resolution.resolve_model_config(object(), "model-record")  # type: ignore[arg-type]

    assert config["api_key"] == ""


@pytest.mark.asyncio
async def test_resolve_legacy_model_config_rejects_invalid_config() -> None:
    with pytest.raises(NotFoundError, match="会话模型配置无法恢复"):
        await model_resolution.resolve_legacy_model_config(
            object(),  # type: ignore[arg-type]
            {"model_id": "model", "provider_type": "openai-compatible"},
        )


@pytest.mark.asyncio
async def test_resolve_legacy_model_config_rejects_unmatched_model(monkeypatch) -> None:
    monkeypatch.setattr(
        model_resolution.model_repo,
        "get_by_legacy_agent_config",
        AsyncMock(return_value=None),
    )

    with pytest.raises(NotFoundError, match="会话模型配置无法恢复"):
        await model_resolution.resolve_legacy_model_config(
            object(),  # type: ignore[arg-type]
            {
                "model_id": "missing-model",
                "provider_type": "openai-compatible",
                "base_url": "https://api.example/v1",
            },
        )
