"""OpenAI and OpenAI-compatible LLM clients."""
from __future__ import annotations

from lib.config import Configuration
from lib.llm.client import DEFAULT_OLLAMA_BASE_URL, resolve_api_key


class OpenAICompatibleClient:
    """Client for OpenAI and OpenAI-compatible APIs."""

    def __init__(self, config: Configuration, provider: str) -> None:
        """Initialize the client from engine.llm config."""
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError(
                "The openai package is required for OpenAI-compatible LLM providers. "
                "Install it with: pip install openai"
            ) from error

        self.model = str(config.lookup("model") or "gpt-4o")
        self.temperature = float(config.lookup("temperature") if config.lookup("temperature") is not None else 0.2)
        self.timeout = float(config.lookup("timeout") if config.lookup("timeout") is not None else 45)
        base_url = config.lookup("base_url")
        if provider == "ollama":
            base_url = base_url or DEFAULT_OLLAMA_BASE_URL
        elif provider == "openai_compatible" and not base_url:
            raise ValueError(
                "engine.llm.base_url is required when provider is openai_compatible."
            )

        client_kwargs: dict[str, object] = {
            "api_key": resolve_api_key(config),
            "timeout": self.timeout,
        }
        if base_url:
            client_kwargs["base_url"] = str(base_url)

        self._client = OpenAI(**client_kwargs)

    def complete(self, system: str, user: str) -> str:
        """Request a completion and return the assistant message text."""
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("LLM returned an empty response.")
        return content.strip()
