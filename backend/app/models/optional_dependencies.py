"""Availability checks for provider SDK extras.

The generic OpenAI-compatible path is part of the base installation.  Native
provider clients stay optional so a saved provider configuration never makes
the application fail to import at startup.
"""

from importlib.util import find_spec

_DEPENDENCIES: dict[tuple[str, str], tuple[str, str]] = {
    ("amazon-nova", "llm"): ("langchain_amazon_nova", "amazon-nova"),
    ("anthropic", "llm"): ("langchain_anthropic", "anthropic"),
    ("anthropic-compatible", "llm"): ("langchain_anthropic", "anthropic"),
    ("cohere", "llm"): ("langchain_cohere", "cohere"),
    ("cohere", "embedding"): ("langchain_cohere", "cohere"),
    ("deepseek", "llm"): ("langchain_deepseek", "deepseek"),
    ("google-genai", "llm"): ("langchain_google_genai", "google-genai"),
    ("google-genai", "embedding"): ("langchain_google_genai", "google-genai"),
    ("groq", "llm"): ("langchain_groq", "groq"),
    ("mistral", "llm"): ("langchain_mistralai", "mistral"),
    ("mistral", "embedding"): ("langchain_mistralai", "mistral"),
    ("nvidia-ai-endpoints", "llm"): ("langchain_nvidia_ai_endpoints", "nvidia"),
    ("nvidia-ai-endpoints", "embedding"): ("langchain_nvidia_ai_endpoints", "nvidia"),
    ("openrouter", "llm"): ("langchain_openrouter", "openrouter"),
}


def required_extra(provider_type: str, task_type: str) -> str | None:
    """Return the optional extra required by one native provider capability."""
    dependency = _DEPENDENCIES.get((provider_type, task_type))
    return dependency[1] if dependency else None


def is_available(provider_type: str, task_type: str) -> bool:
    """Check an optional SDK without importing it or making a network request."""
    dependency = _DEPENDENCIES.get((provider_type, task_type))
    return dependency is None or find_spec(dependency[0]) is not None


def install_hint(provider_type: str, task_type: str) -> str | None:
    """Return a copyable installation command when this capability is absent."""
    extra = required_extra(provider_type, task_type)
    if extra and not is_available(provider_type, task_type):
        return f"uv sync --extra {extra}"
    return None
