"""Anthropic Claude LLM client."""
from __future__ import annotations

from lib.config import Configuration
from lib.llm.client import resolve_api_key


class AnthropicClient:
    """Client for Anthropic's Messages API."""

    def __init__(self, config: Configuration) -> None:
        """Initialize the client from engine.llm config."""
        try:
            from anthropic import Anthropic
        except ImportError as error:
            raise RuntimeError(
                "The anthropic package is required for the anthropic LLM provider. "
                "Install it with: pip install anthropic"
            ) from error

        self.model = str(config.lookup("model") or "claude-sonnet-4-20250514")
        self.temperature = float(config.lookup("temperature") if config.lookup("temperature") is not None else 0.2)
        self.timeout = float(config.lookup("timeout") if config.lookup("timeout") is not None else 45)
        self._client = Anthropic(
            api_key=resolve_api_key(config),
            timeout=self.timeout,
        )

    def complete(self, system: str, user: str) -> str:
        """Request a completion and return the assistant message text."""
        response = self._client.messages.create(
            model=self.model,
            max_tokens=16,
            temperature=self.temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text_blocks = [block.text for block in response.content if block.type == "text"]
        if not text_blocks:
            raise RuntimeError("LLM returned an empty response.")
        return text_blocks[0].strip()
