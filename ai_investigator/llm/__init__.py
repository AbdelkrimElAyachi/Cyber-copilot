"""LLM provider package — factory and re-exports."""

from __future__ import annotations

from typing import Any

from .base import LLMProvider, LLMResponse, ToolCall
from .api_provider import APIProvider
from .local_provider import LocalProvider

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "ToolCall",
    "APIProvider",
    "LocalProvider",
    "create_provider",
]


def create_provider(provider_type: str, **kwargs: Any) -> LLMProvider:
    """Factory — create an LLM provider by type name.

    Args:
        provider_type: ``"api"`` for a remote API or ``"local"`` for Ollama.
        **kwargs: Passed to the provider constructor (base_url, model, etc.).
    """
    if provider_type == "local":
        return LocalProvider(**kwargs)
    if provider_type == "api":
        return APIProvider(**kwargs)
    raise ValueError(f"Unknown LLM provider type: {provider_type!r}")
