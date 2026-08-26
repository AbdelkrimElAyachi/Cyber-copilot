"""
AI Investigator — autonomous security investigation engine.

Receives a Wazuh alert and an investigation ID, then runs an
agentic tool-calling loop: the LLM analyses the alert, decides
what additional context it needs, calls tools, and repeats until
it reaches a verdict.

Every tool call is recorded in ``investigation_actions``.
The final verdict is stored in ``investigation_analysis``.

Usage:
    from ai_investigator.investigator import AIInvestigator
    from ai_investigator.llm import create_provider

    llm = create_provider("api", base_url="...", model="...", api_key="...")
    investigator = AIInvestigator(llm=llm, db=db, alert_receiver=receiver)
    result = investigator.investigate(investigation_id, alert_data)
"""

from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime
from typing import Any, Optional

from database import Database, new_id
from alert_receiver import AlertReceiver
from ai_investigator.llm.base import LLMProvider, LLMResponse
from ai_investigator.tools.base import Tool

logger = logging.getLogger("ai_investigator")

# Maximum tool-calling iterations to prevent infinite loops.
MAX_STEPS = 10

# Tool results are sent back to the LLM in full on every subsequent call
# (chat completions are stateless — the whole history is resent each
# time), so an unbounded tool result compounds across steps and can blow
# past the API's request-size limit (413). Cap what actually goes into
# the conversation the LLM sees.
MAX_TOOL_RESULT_CHARS = 1500

# Hard cap on the total size (JSON-serialised, in characters) of the
# conversation sent to the LLM. Per-message truncation alone isn't
# enough — many small, individually-fine tool results still compound
# across a long tool-calling loop into an oversized request. Once the
# running total would cross this, the loop stops calling tools early and
# asks for a final verdict with whatever context was gathered so far,
# instead of letting the next request blow past the API's size limit.
MAX_CONVERSATION_CHARS = 20_000

# ── System prompt ───────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are an expert AI security analyst working on a Security Investigation Platform.

Your task: investigate a security alert and determine whether it is a TRUE POSITIVE, \
FALSE POSITIVE, or REQUIRES FURTHER INVESTIGATION.

## Investigation Process

1. Carefully analyse the triggering alert provided to you.
2. Use your tools to gather additional context:
   - Search for related alerts from the same agent, IP, or rule.
   - Look up the asset involved (hostname, IP, agent ID).
   - Check for existing investigations that may be related.
   - Examine evidence and analysis from related investigations.
3. Correlate all evidence to form your assessment.
4. Provide your final verdict.

## Guidelines

- Be thorough but efficient. Only call tools when you need more information.
- Think step-by-step. Explain your reasoning.
- Do NOT fabricate information. Only use data from your tools.
- If the data is insufficient, say so honestly.
- Each tool call should have a clear purpose.

## Final Verdict Format

When you reach your conclusion, clearly state:
- **Verdict**: TRUE_POSITIVE, FALSE_POSITIVE, or NEEDS_REVIEW
- **Confidence**: a number from 0.0 to 1.0
- **Severity Assessment**: low, medium, high, or critical
- **Summary**: 2-3 sentence executive summary
- **Details**: Full analysis with evidence references
- **Recommended Actions**: Numbered list of next steps
"""


def _bounded_json(obj: Any, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
    """Serialise ``obj`` to JSON, truncating if it exceeds ``limit`` chars."""
    text = json.dumps(obj, default=str)
    if len(text) <= limit:
        return text
    return (
        text[:limit]
        + f"... [truncated, {len(text)} chars total — narrow your query for more targeted results]"
    )


def _conversation_size(messages: list[dict[str, Any]]) -> int:
    """Approximate the JSON-serialised size (chars) of the conversation —
    a close proxy for the actual request body size, since ``messages`` is
    the bulk of what's sent to the LLM API."""
    return len(json.dumps(messages, default=str))


class AIInvestigator:
    """Autonomous security investigation engine powered by an LLM.

    The investigator runs a tool-calling loop: it sends the alert
    to the LLM, the LLM calls tools to gather context, and the
    loop continues until the LLM produces a final verdict.
    """

    def __init__(
        self,
        llm: LLMProvider,
        db: Database,
        alert_receiver: Optional[AlertReceiver] = None,
        max_steps: int = MAX_STEPS,
    ) -> None:
        self._llm = llm
        self._db = db
        self._receiver = alert_receiver
        self._max_steps = max_steps
        self._tools: dict[str, Tool] = {}
        self._register_tools()

    # ── Tool registration ───────────────────────────────────────────

    def _register_tools(self) -> None:
        """Register all available tools."""
        from ai_investigator.tools.wazuh_tools import (
            SearchAlertsTool,
            GetAlertDetailsTool,
        )
        from ai_investigator.tools.database_tools import (
            SearchInvestigationsTool,
            GetInvestigationTool,
            GetInvestigationEvidenceTool,
            GetInvestigationAnalysisTool,
            SearchAssetsTool,
            GetAssetTool,
        )

        # Wazuh tools (only if receiver is available).
        if self._receiver is not None:
            self._add_tool(SearchAlertsTool(self._receiver))
            self._add_tool(GetAlertDetailsTool(self._receiver))

        # Database tools.
        self._add_tool(SearchInvestigationsTool(self._db))
        self._add_tool(GetInvestigationTool(self._db))
        self._add_tool(GetInvestigationEvidenceTool(self._db))
        self._add_tool(GetInvestigationAnalysisTool(self._db))
        self._add_tool(SearchAssetsTool(self._db))
        self._add_tool(GetAssetTool(self._db))

    def _add_tool(self, tool: Tool) -> None:
        """Register a single tool."""
        self._tools[tool.name] = tool

    # ── Public API ──────────────────────────────────────────────────

    def investigate(
        self,
        investigation_id: str,
        alert_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Run a full investigation on the given alert.

        Args:
            investigation_id: The UUID of the investigation to process.
            alert_data: The full Wazuh alert dict that triggered it.

        Returns:
            A dict with the investigation result (verdict, confidence, etc.).
        """
        logger.info("Starting investigation %s", investigation_id)

        try:
            # Mark investigation as in-progress.
            self._db.execute(
                "UPDATE investigations SET status = %s WHERE id = %s",
                ("IN_PROGRESS", investigation_id),
            )

            # Store the triggering alert as evidence.
            self._store_evidence(
                investigation_id,
                source_type="wazuh_alert",
                source_id=alert_data.get("id"),
                data=alert_data,
                notes="Triggering alert.",
            )

            result = self._run_loop(investigation_id, alert_data)

            # Store the final analysis.
            self._store_analysis(
                investigation_id,
                content=result.get("details", result.get("summary", "")),
                confidence=result.get("confidence"),
                verdict=result.get("verdict"),
            )

            # Update investigation status.
            final_status = "COMPLETED"
            self._db.execute(
                "UPDATE investigations SET status = %s WHERE id = %s",
                (final_status, investigation_id),
            )

            logger.info(
                "Investigation %s completed: %s (confidence: %s)",
                investigation_id,
                result.get("verdict", "unknown"),
                result.get("confidence", "?"),
            )
            return result

        except Exception as e:
            logger.error("Investigation %s failed: %s", investigation_id, e)
            traceback.print_exc()

            # Record the error. Everything below is best-effort — this
            # investigation must not stay stuck at IN_PROGRESS forever
            # just because a *second* thing (e.g. the DB write itself)
            # also fails; this runs as a fire-and-forget background task,
            # so an uncaught exception here would be silently swallowed
            # by the caller with the status never getting updated.
            try:
                self._store_analysis(
                    investigation_id,
                    content=f"Investigation failed with error: {e}",
                    confidence=0.0,
                    verdict="ERROR",
                )
            except Exception as e2:
                logger.error(
                    "Investigation %s — also failed to record the error analysis: %s",
                    investigation_id, e2,
                )

            try:
                self._db.execute(
                    "UPDATE investigations SET status = %s WHERE id = %s",
                    ("COMPLETED", investigation_id),
                )
            except Exception as e3:
                logger.error(
                    "Investigation %s — also failed to update final status: %s",
                    investigation_id, e3,
                )

            return {"verdict": "ERROR", "error": str(e)}

    # ── Agentic loop ────────────────────────────────────────────────

    def _run_loop(
        self,
        investigation_id: str,
        alert_data: dict[str, Any],
    ) -> dict[str, Any]:
        """The core tool-calling loop."""

        # Build initial messages.
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Investigate this security alert:\n\n"
                    f"```json\n{json.dumps(alert_data, indent=2, default=str)}\n```\n\n"
                    "Use your tools to gather additional context, then provide "
                    "your verdict."
                ),
            },
        ]

        # Tool schemas for the LLM.
        tool_schemas = [tool.schema() for tool in self._tools.values()]

        for step in range(self._max_steps):
            logger.info("Investigation %s — step %d", investigation_id, step + 1)

            # Call the LLM.
            response = self._llm.chat(messages, tools=tool_schemas)

            # If the LLM produced text without tool calls → verdict.
            if not response.has_tool_calls:
                final_text = response.content or ""
                if not final_text.strip():
                    # Some models (e.g. Groq's gpt-oss family) can return an
                    # empty "content" — they spent their token budget on an
                    # internal "reasoning" field instead of ever writing a
                    # final answer. Treat that as a failure instead of
                    # silently storing a blank analysis.
                    raise RuntimeError(
                        "LLM returned an empty response with no tool calls "
                        "(it may have run out of output tokens before "
                        "writing a final answer — try increasing LLM_MAX_TOKENS)"
                    )
                logger.info("Investigation %s — LLM produced final answer", investigation_id)
                return self._parse_verdict(final_text)

            # Process each tool call.
            # Add the assistant message with tool calls to the conversation.
            # `content` must be `None`, not `""` — some providers (Groq's
            # gpt-oss models included) reject a tool-calling assistant
            # message whose content is an empty string rather than null.
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": response.content or None}
            if response.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in response.tool_calls
                ]
            messages.append(assistant_msg)

            # What the AI understood/decided before making these tool
            # calls — recorded on each action so a human can see why it
            # acted, not just what it called.
            reasoning = response.reasoning_text or None

            for tc in response.tool_calls:
                tool_result = self._execute_tool(
                    investigation_id, tc.name, tc.arguments, reasoning=reasoning
                )

                # Add tool result to conversation (bounded — see
                # MAX_TOOL_RESULT_CHARS).
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": _bounded_json(tool_result),
                })

            if _conversation_size(messages) >= MAX_CONVERSATION_CHARS:
                logger.warning(
                    "Investigation %s — conversation reached %d chars, "
                    "forcing verdict early instead of risking an "
                    "oversized request",
                    investigation_id, _conversation_size(messages),
                )
                return self._force_final_verdict(investigation_id, messages)

        # Hit max steps — ask for a final answer without tools.
        logger.warning(
            "Investigation %s hit max steps (%d), forcing verdict",
            investigation_id,
            self._max_steps,
        )
        return self._force_final_verdict(investigation_id, messages)

    def _force_final_verdict(
        self,
        investigation_id: str,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Ask the LLM for a final verdict, no more tool calls allowed."""
        messages.append({
            "role": "user",
            "content": (
                "You have reached the maximum context for this investigation. "
                "Based on all the information gathered so far, provide "
                "your final verdict now."
            ),
        })
        response = self._llm.chat(messages, tools=None)
        final_text = response.content or ""
        if not final_text.strip():
            raise RuntimeError(
                f"LLM returned an empty forced final answer for investigation "
                f"{investigation_id} (it may have run out of output tokens — "
                "try increasing LLM_MAX_TOKENS)"
            )
        return self._parse_verdict(final_text)

    # ── Tool execution ──────────────────────────────────────────────

    def _execute_tool(
        self,
        investigation_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        reasoning: Optional[str] = None,
    ) -> Any:
        """Execute a tool and record the action."""
        tool = self._tools.get(tool_name)
        if tool is None:
            error_msg = f"Unknown tool: {tool_name}"
            logger.warning(error_msg)
            self._record_action(
                investigation_id, tool_name,
                description=json.dumps(arguments),
                reasoning=reasoning,
                status="failed", result=error_msg,
            )
            return {"error": error_msg}

        logger.info("  → calling %s(%s)", tool_name, arguments)

        try:
            result = tool.execute(**arguments)

            # Record the action.
            result_str = json.dumps(result, default=str)
            # Truncate very long results for the action log.
            result_summary = result_str[:2000] + "..." if len(result_str) > 2000 else result_str
            self._record_action(
                investigation_id, tool_name,
                description=json.dumps(arguments),
                reasoning=reasoning,
                status="completed", result=result_summary,
            )
            return result

        except Exception as e:
            error_msg = f"Tool error: {e}"
            logger.error("  → %s failed: %s", tool_name, e)
            self._record_action(
                investigation_id, tool_name,
                description=json.dumps(arguments),
                reasoning=reasoning,
                status="failed", result=error_msg,
            )
            return {"error": error_msg}

    # ── Database helpers ────────────────────────────────────────────

    def _record_action(
        self,
        investigation_id: str,
        action_type: str,
        description: str,
        status: str,
        result: str,
        reasoning: Optional[str] = None,
    ) -> None:
        """Record a tool call in investigation_actions."""
        self._db.execute(
            "INSERT INTO investigation_actions "
            "(id, investigation_id, action_type, description, reasoning, status, result, "
            "performed_by, created_at, completed_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, NOW(), NOW())",
            (
                new_id(),
                investigation_id,
                action_type,
                description,
                reasoning,
                status,
                result,
            ),
        )

    def _store_evidence(
        self,
        investigation_id: str,
        source_type: str,
        source_id: Optional[str],
        data: Any,
        notes: str,
    ) -> None:
        """Store a piece of evidence."""
        self._db.execute(
            "INSERT INTO investigation_evidence "
            "(id, investigation_id, source_type, source_id, data, notes) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                new_id(),
                investigation_id,
                source_type,
                source_id,
                json.dumps(data, default=str),
                notes,
            ),
        )

    def _store_analysis(
        self,
        investigation_id: str,
        content: str,
        confidence: Optional[float] = None,
        verdict: Optional[str] = None,
    ) -> None:
        """Store the AI's final analysis."""
        self._db.execute(
            "INSERT INTO investigation_analysis "
            "(id, investigation_id, analysis_type, verdict, content, confidence, model_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                new_id(),
                investigation_id,
                "ai",
                verdict,
                content,
                confidence,
                getattr(self._llm, "model", None),
            ),
        )

    # ── Verdict parser ──────────────────────────────────────────────

    @staticmethod
    def _parse_verdict(text: str) -> dict[str, Any]:
        """Extract structured verdict from the LLM's final text.

        Tries to find a JSON block first, falls back to text parsing.
        """
        # Try to extract JSON from the response.
        import re

        json_match = re.search(r"```json\s*(.*?)```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try raw JSON.
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass

        # Fall back to text-based parsing.
        verdict: dict[str, Any] = {
            "raw_response": text,
        }

        # Extract verdict.
        verdict_match = re.search(
            r"\*?\*?Verdict\*?\*?\s*:?\s*(TRUE_POSITIVE|FALSE_POSITIVE|NEEDS_REVIEW)",
            text, re.IGNORECASE,
        )
        if verdict_match:
            verdict["verdict"] = verdict_match.group(1).upper()

        # Extract confidence.
        conf_match = re.search(
            r"\*?\*?Confidence\*?\*?\s*:?\s*([\d.]+)", text
        )
        if conf_match:
            try:
                verdict["confidence"] = float(conf_match.group(1))
            except ValueError:
                pass

        # Extract summary.
        summary_match = re.search(
            r"\*?\*?Summary\*?\*?\s*:?\s*(.+?)(?:\n\n|\*\*|$)",
            text, re.DOTALL,
        )
        if summary_match:
            verdict["summary"] = summary_match.group(1).strip()

        # Store full text as details if we couldn't parse it.
        if "verdict" not in verdict:
            verdict["verdict"] = "NEEDS_REVIEW"
            verdict["details"] = text

        if "details" not in verdict:
            verdict["details"] = text

        return verdict
