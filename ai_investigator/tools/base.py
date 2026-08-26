"""Tool base class for the AI Investigator."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """Base class for tools that the AI Investigator can call."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name (used in LLM function calling)."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what the tool does."""
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for the tool's parameters."""
        ...

    @abstractmethod
    def execute(self, **kwargs: Any) -> Any:
        """Run the tool with the given arguments and return the result."""
        ...

    def schema(self) -> dict[str, Any]:
        """Return the OpenAI function-calling schema for this tool."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
