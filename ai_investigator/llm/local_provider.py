"""Local LLM provider via Ollama (OpenAI-compatible endpoint)."""

from __future__ import annotations

from .api_provider import APIProvider


class LocalProvider(APIProvider):
    """LLM provider for a local model running on Ollama.

    Ollama exposes an OpenAI-compatible API at ``/v1/chat/completions``,
    so this is just an APIProvider with different defaults and no API key.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        model: str = "llama3",
        temperature: float = 0.1,
        max_tokens: int | None = 4096,
    ) -> None:
        super().__init__(
            base_url=base_url,
            model=model,
            api_key=None,
            temperature=temperature,
            max_tokens=max_tokens,
        )
