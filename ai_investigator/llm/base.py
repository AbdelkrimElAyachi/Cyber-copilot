"""LLM provider abstraction — base classes and response types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolCall:
    """A single tool call requested by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Response from an LLM provider."""

    content: Optional[str] = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    # Some providers (e.g. Groq's gpt-oss models) return the model's
    # chain-of-thought in a separate field instead of/alongside `content`,
    # especially on turns where it only calls tools and writes no
    # user-facing text. Captured so investigation_actions can record why
    # the AI made each tool call, not just which tool and what arguments.
    reasoning: Optional[str] = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    @property
    def reasoning_text(self) -> str:
        """Best-effort explanation for this turn: prefer `content` (what
        the model actually said), fall back to `reasoning` (its internal
        chain-of-thought) when content is empty."""
        return (self.content or self.reasoning or "").strip()


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict]] = None,
    ) -> LLMResponse:
        """Send messages with optional tool definitions and return a response."""
        ...
