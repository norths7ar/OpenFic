"""
Adapter registry tests.
"""

from app.models import optional_dependencies
from app.models.registry import AdapterRegistry


def test_registry_lists_only_current_first_class_provider_types() -> None:
    assert set(AdapterRegistry.list_providers()) == {
        "openai",
        "anthropic",
        "google-genai",
        "ollama",
        "groq",
        "huggingface",
        "mistral",
        "nvidia-ai-endpoints",
        "cohere",
        "openrouter",
        "amazon-nova",
        "deepseek",
        "openai-compatible",
        "openai-compatible-responses",
        "anthropic-compatible",
    }
    assert "google-vertex" not in AdapterRegistry.list_providers()


def test_registry_reports_missing_native_sdk_per_provider_task(monkeypatch) -> None:
    monkeypatch.setattr(optional_dependencies, "find_spec", lambda _module: None)

    assert AdapterRegistry.is_available("openai-compatible", "llm")
    assert not AdapterRegistry.is_available("deepseek", "llm")
    assert AdapterRegistry.unavailable_reason("deepseek", "llm") == "uv sync --extra deepseek"
    assert AdapterRegistry.unavailable_reason("deepseek", "embedding") is None
