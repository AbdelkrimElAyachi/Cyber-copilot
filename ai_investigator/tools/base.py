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

    def coerce_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Loosely cast argument values to match this tool's declared JSON
        Schema types, e.g. ``{"limit": "50"}`` -> ``{"limit": 50}``.

        Tool-call arguments come from an LLM's JSON generation, and models
        (local or API, any provider) sometimes emit a number as a string
        even when the schema says "integer"/"number" — that's not a
        provider-specific quirk to special-case, it's just JSON generated
        by a language model. Individual tools shouldn't each have to
        defend against it (e.g. ``min(limit, 50)`` breaks if ``limit`` is
        a str), so it's handled once, here, before any tool sees the
        arguments. A value that doesn't look like a number is left alone —
        the tool's own error handling still reports something meaningful.
        """
        props = self.parameters.get("properties", {})
        coerced = dict(arguments)
        for key, spec in props.items():
            if key not in coerced or not isinstance(coerced[key], str):
                continue
            expected = spec.get("type")
            raw = coerced[key].strip()
            try:
                if expected == "integer":
                    coerced[key] = int(raw)
                elif expected == "number":
                    coerced[key] = float(raw)
                elif expected == "boolean" and raw.lower() in ("true", "false"):
                    coerced[key] = raw.lower() == "true"
            except ValueError:
                pass  # leave as-is; execute()/validation surfaces the problem
        return coerced
