"""LLM client factory and shared helpers."""
from __future__ import annotations

import os
from typing import Protocol

from lib.config import Configuration

SUPPORTED_PROVIDERS = ("openai", "anthropic", "ollama", "openai_compatible")
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"


class LLMClient(Protocol):
    """Interface for LLM providers used by LLMEngine."""

    def complete(self, system: str, user: str) -> str:
        """Return the model's text response."""
        ...


def resolve_api_key(config: Configuration) -> str:
    """Load an API key from config or environment."""
    api_key_env = config.lookup("api_key_env")
    if api_key_env:
        value = os.environ.get(str(api_key_env), "")
        if value:
            return value

    api_key = config.lookup("api_key")
    if api_key:
        return str(api_key)

    provider = str(config.lookup("provider") or "")
    if provider == "ollama":
        return "ollama"

    env_name = api_key_env or "OPENAI_API_KEY"
    raise RuntimeError(
        f"Missing API key for LLM provider {provider!r}. "
        f"Set environment variable {env_name} or engine.llm.api_key in config.yml."
    )


def create_client(config: Configuration) -> LLMClient:
    """Create an LLM client for the configured provider."""
    provider = str(config.lookup("provider") or "openai")
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported LLM provider {provider!r}. "
            f"Choose from: {', '.join(SUPPORTED_PROVIDERS)}."
        )

    if provider == "anthropic":
        from lib.llm.anthropic import AnthropicClient

        return AnthropicClient(config)

    if provider == "ollama":
        from lib.llm.ollama import OllamaClient

        return OllamaClient(config)

    from lib.llm.openai_compatible import OpenAICompatibleClient

    return OpenAICompatibleClient(config, provider=provider)
