"""OpenAI-compatible API provider for remote LLMs."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

import requests

from .base import LLMProvider, LLMResponse, ToolCall, ToolChoiceViolationError

logger = logging.getLogger("ai_investigator.llm")

# Retry behavior for transient errors (rate limits, momentary outages).
# Rate limits on shared/free-tier API keys are common enough during an
# agentic loop (many requests in a row) that a naive immediate failure
# would abort otherwise-recoverable investigations.
MAX_RETRIES = 4
BASE_BACKOFF_SECONDS = 2.0

# A server-supplied Retry-After can be large enough that it's no longer a
# brief burst limit — it's the provider saying a quota is exhausted and
# won't recover soon. A background investigation blindly sleeping through
# that (we've seen Retry-After: 1770, i.e. ~30 minutes) is indistinguishable
# from a hang. Cap how long we'll actually wait; past this, fail fast with
# a clear message instead of blocking the caller.
MAX_RETRY_WAIT_SECONDS = 60.0


class APIProvider(LLMProvider):
    """LLM provider that calls an OpenAI-compatible chat completions API.

    Works with OpenAI, Groq, Together, Mistral, Azure OpenAI, and any
    other provider that implements the ``/chat/completions`` endpoint.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = 4096,
        reasoning_effort: Optional[str] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._temperature = temperature
        # Explicit output cap. Some providers (e.g. Groq's gpt-oss models,
        # which emit chain-of-thought in a separate "reasoning" field
        # before the final "content") apply their own default that can be
        # too small, cutting the response off before "content" is ever
        # written — resulting in an empty final answer. Setting this
        # explicitly gives the model enough room to reason AND answer.
        self._max_tokens = max_tokens
        # Groq's gpt-oss models (and OpenAI's o-series) accept this to cap
        # how many tokens they spend on internal chain-of-thought before
        # writing "content". Lower effort = fewer tokens per call = faster
        # responses and less pressure on tokens-per-minute quotas, at some
        # cost to reasoning depth. Ignored by providers that don't support
        # it, so it's only sent when explicitly configured.
        self._reasoning_effort = reasoning_effort

    @property
    def model(self) -> str:
        """The model name used for chat completions (recorded on analyses)."""
        return self._model

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[str] = None,
    ) -> LLMResponse:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
        }
        if self._max_tokens:
            payload["max_tokens"] = self._max_tokens
        if self._reasoning_effort:
            payload["reasoning_effort"] = self._reasoning_effort
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"
        elif tool_choice:
            # Forcing "none" with no tools declared at all is what
            # actually triggers some providers (Groq's gpt-oss models) to
            # ignore the constraint and attempt a tool call anyway, which
            # they then reject outright. Send it explicitly even without a
            # tools list so the intent is unambiguous.
            payload["tool_choice"] = tool_choice

        url = f"{self._base_url}/chat/completions"
        logger.debug("POST %s model=%s", url, self._model)

        data = self._post_with_retry(url, payload, headers)

        choice = data["choices"][0]
        message = choice["message"]

        # Parse tool calls if present.
        tool_calls: list[ToolCall] = []
        if message.get("tool_calls"):
            for tc in message["tool_calls"]:
                try:
                    args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, KeyError):
                    args = {}
                tool_calls.append(
                    ToolCall(
                        id=tc.get("id", ""),
                        name=tc["function"]["name"],
                        arguments=args,
                    )
                )

        return LLMResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            reasoning=message.get("reasoning"),
        )

    def _post_with_retry(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """POST with retry/backoff for rate limits (429) and transient
        server errors (5xx). Anything else (bad request, auth, model not
        found, ...) fails immediately since retrying won't help.
        """
        last_error: Optional[Exception] = None
        for attempt in range(MAX_RETRIES + 1):
            resp = requests.post(url, json=payload, headers=headers, timeout=120)
            if resp.status_code not in (429, 500, 502, 503, 504):
                if not resp.ok:
                    if resp.status_code == 400:
                        violation = self._detect_tool_choice_violation(resp)
                        if violation is not None:
                            raise violation
                    raise requests.exceptions.HTTPError(
                        f"{resp.status_code} Client Error for url: {url} | "
                        f"response body: {resp.text[:1000]}",
                        response=resp,
                    )
                return resp.json()

            last_error = requests.exceptions.HTTPError(
                f"{resp.status_code} Client/Server Error for url: {url} | "
                f"response body: {resp.text[:1000]}",
                response=resp,
            )
            if attempt == MAX_RETRIES:
                break

            retry_after = resp.headers.get("Retry-After")
            if retry_after is not None:
                try:
                    wait = float(retry_after)
                except ValueError:
                    wait = BASE_BACKOFF_SECONDS * (2 ** attempt)
            else:
                wait = BASE_BACKOFF_SECONDS * (2 ** attempt)

            if wait > MAX_RETRY_WAIT_SECONDS:
                # Don't block on this — it's a quota exhaustion, not a
                # brief limit. Fail now with a message that says exactly
                # why and how long the server actually wants us to wait,
                # so it's diagnosable instead of looking like a hang.
                raise requests.exceptions.HTTPError(
                    f"{resp.status_code} rate limit for url: {url} — server "
                    f"requested a {wait:.0f}s wait, which exceeds the "
                    f"{MAX_RETRY_WAIT_SECONDS:.0f}s cap. Not retrying "
                    f"(likely a quota limit, not a brief rate limit) | "
                    f"response body: {resp.text[:1000]}",
                    response=resp,
                )

            logger.warning(
                "LLM API returned %s, retrying in %.1fs (attempt %d/%d)",
                resp.status_code, wait, attempt + 1, MAX_RETRIES,
            )
            time.sleep(wait)

        assert last_error is not None
        raise last_error

    @staticmethod
    def _detect_tool_choice_violation(
        resp: "requests.Response",
    ) -> Optional[ToolChoiceViolationError]:
        """Recognise Groq's ``tool_use_failed`` / "Tool choice is none, but
        model called a tool" error body and turn it into a distinguishable
        exception the caller can recover from, instead of a generic 400."""
        try:
            body = resp.json()
        except ValueError:
            return None
        err = body.get("error") if isinstance(body, dict) else None
        if not isinstance(err, dict) or err.get("code") != "tool_use_failed":
            return None
        message = err.get("message") or "Tool choice is none, but model called a tool"
        if "tool choice is none" not in message.lower():
            return None
        attempted: Optional[dict] = None
        raw = err.get("failed_generation")
        if raw:
            try:
                attempted = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                attempted = {"raw": raw}
        return ToolChoiceViolationError(message, attempted_tool_call=attempted)
