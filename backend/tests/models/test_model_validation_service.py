import pytest

from app.core.encryption import EncryptionService
from app.models.clients.embedding_client import EmbeddingClient
from app.models.clients.llm_client import LLMClient
from app.models.clients.rerank_client import RerankClient
from app.models.entities.model import Model
from app.models.entities.model_provider import ModelProvider
from app.models.registry import AdapterRegistry
from app.models.services.model_validation_service import ModelValidationService


def _provider(encryption_service: EncryptionService) -> ModelProvider:
    return ModelProvider(
        name="Test Provider",
        url="https://api.example.com/v1",
        api_key_encrypted=encryption_service.encrypt("test-key"),
        provider_type="openai",
    )


def _encryption_service() -> EncryptionService:
    return EncryptionService("id-hEPdEELwlgep9FQhcYQtX7ow188l7WHwy65qOZGQ=")


def _llm_model(provider: ModelProvider) -> Model:
    return Model(
        name="Test model",
        provider_id=provider.id,
        model_id="test-model",
        task_type="llm",
    )


@pytest.mark.asyncio
async def test_llm_validation_uses_minimal_non_reasoning_request(monkeypatch):
    encryption_service = _encryption_service()
    provider = _provider(encryption_service)
    model = _llm_model(provider)
    captured = {}

    async def generate(self, messages, timeout=None):
        captured["config"] = self.config
        captured["messages"] = messages
        captured["timeout"] = timeout

    monkeypatch.setattr(LLMClient, "generate", generate)

    result = await ModelValidationService(encryption_service).validate(model, provider)

    assert result.success is True
    assert captured["config"].max_tokens == 1
    assert captured["config"].reasoning_effort == "off"
    assert captured["config"].temperature == 0
    assert captured["timeout"] == 20
    assert captured["messages"] == [{"role": "user", "content": "Reply: OK"}]


@pytest.mark.asyncio
async def test_validation_classifies_missing_model(monkeypatch):
    encryption_service = _encryption_service()
    provider = _provider(encryption_service)
    model = _llm_model(provider)

    class ModelNotFound(Exception):
        status_code = 404

    async def generate(self, messages, timeout=None):
        raise ModelNotFound("The model does not exist")

    monkeypatch.setattr(LLMClient, "generate", generate)

    result = await ModelValidationService(encryption_service).validate(model, provider)

    assert result.success is False
    assert result.error_code == "model_not_found"
    assert result.detail == "The model does not exist"


@pytest.mark.asyncio
async def test_embedding_validation_uses_one_short_input(monkeypatch):
    encryption_service = _encryption_service()
    provider = _provider(encryption_service)
    model = Model(
        name="Embedding model",
        provider_id=provider.id,
        model_id="embedding-model",
        task_type="embedding",
        dimensions=768,
    )
    captured = {}

    async def embed_single(self, text):
        captured["config"] = self.config
        captured["text"] = text
        return [0.0]

    monkeypatch.setattr(EmbeddingClient, "embed_single", embed_single)

    result = await ModelValidationService(encryption_service).validate(model, provider)

    assert result.success is True
    assert captured["text"] == "OpenFic"
    assert captured["config"].batch_size == 1
    assert captured["config"].dimensions == 768


@pytest.mark.asyncio
async def test_rerank_validation_uses_one_document(monkeypatch):
    encryption_service = _encryption_service()
    provider = _provider(encryption_service)
    model = Model(
        name="Rerank model",
        provider_id=provider.id,
        model_id="rerank-model",
        task_type="rerank",
    )
    captured = {}

    async def rerank(self, query, documents, top_n=None):
        captured["query"] = query
        captured["documents"] = documents
        captured["top_n"] = top_n
        captured["timeout"] = self.config.request_timeout

    monkeypatch.setattr(RerankClient, "rerank", rerank)

    result = await ModelValidationService(encryption_service).validate(model, provider)

    assert result.success is True
    assert captured == {
        "query": "OpenFic",
        "documents": ["connection test"],
        "top_n": 1,
        "timeout": 20,
    }


@pytest.mark.asyncio
async def test_validation_rejects_unsupported_task_type(monkeypatch):
    encryption_service = _encryption_service()
    provider = _provider(encryption_service)
    model = _llm_model(provider)
    monkeypatch.setattr(
        AdapterRegistry,
        "is_supported",
        classmethod(lambda cls, *_: False),
    )

    result = await ModelValidationService(encryption_service).validate(model, provider)

    assert result.success is False
    assert result.error_code == "capability_incompatible"


@pytest.mark.asyncio
async def test_validation_explains_missing_provider_extra(monkeypatch):
    encryption_service = _encryption_service()
    provider = _provider(encryption_service)
    model = _llm_model(provider)
    monkeypatch.setattr(
        AdapterRegistry,
        "unavailable_reason",
        classmethod(lambda cls, *_: "uv sync --extra deepseek"),
    )

    result = await ModelValidationService(encryption_service).validate(model, provider)

    assert result.success is False
    assert result.error_code == "capability_incompatible"
    assert result.message == "此提供商的 llm 适配未安装，请运行 uv sync --extra deepseek。"
