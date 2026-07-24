"""Ollama LLM client (OpenAI-compatible endpoint)."""
from __future__ import annotations

from lib.config import Configuration
from lib.llm.openai_compatible import OpenAICompatibleClient


class OllamaClient(OpenAICompatibleClient):
    """Thin wrapper around the OpenAI-compatible Ollama endpoint."""

    def __init__(self, config: Configuration) -> None:
        """Initialize the Ollama client."""
        super().__init__(config, provider="ollama")
