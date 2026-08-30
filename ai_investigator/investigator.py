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
from ai_investigator.llm.base import LLMProvider, LLMResponse, ToolChoiceViolationError
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

1. Carefully analyse the triggering alert AND the baseline context already
   provided below it (the asset record and recent alert history for this
   same agent are fetched for you up front — read them before calling any
   tool, they usually answer "is this normal for this host?" by themselves).
2. Only call tools for what the baseline context doesn't already answer:
   - A different agent, IP, rule, or time range than what's already shown.
   - Related or past investigations that might explain the pattern.
   - Full detail on a specific alert the summary above truncated.
3. Correlate all evidence to form your assessment.
4. Provide your final verdict.

## Efficiency — this matters as much as accuracy

- Most alerts should reach a verdict in 2-4 tool calls, using the baseline
  context already given. Reserve more than that for genuinely ambiguous cases.
- Never repeat a search with near-identical arguments hoping for a different
  answer (e.g. the same query reworded, or the same rule_id looked up twice).
  The platform detects and blocks exact duplicate calls — reusing one wastes
  a step for nothing. If a search came back thin, either broaden it in a way
  that would actually change the result (different agent/IP/rule/time range)
  or conclude from what you have.
- If a step needs more than one independent lookup (e.g. the asset record
  AND a related-investigations search), call both tools in that same turn
  instead of one per turn.
- A single, low-severity alert with no corroborating signal and an obvious
  benign explanation does not need five searches to confirm it's benign.

## Known benign patterns (verify briefly, don't over-investigate)

- Wazuh agent ID `000` is the Wazuh manager/server itself, not a monitored
  endpoint — alerts from it often reflect the platform's own operation.
- Creation of system groups/users named `wazuh-*` (e.g. `wazuh-dashboard`,
  `wazuh-indexer`) is routine self-provisioning by the Wazuh stack during
  install/upgrade, not an attacker creating accounts — unless it recurs
  unexpectedly long after initial setup, or is paired with other suspicious
  activity (new SSH keys, sudoers changes, unfamiliar binaries).
- Listening-port-changed (netstat) alerts are frequently just a service
  restarting; only escalate if the new port/process is unfamiliar.

## Guidelines

- Do NOT fabricate information. Only use data from your tools.
- If the data is insufficient, say so honestly.
- Each tool call should have a clear purpose distinct from prior calls.

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

            # Pre-fetch the context the LLM almost always ends up asking for
            # anyway (the asset record, recent history for the same agent)
            # in one local pass instead of making it spend tool-call steps
            # (and LLM round-trips) discovering it. Faster, and cheaper on
            # rate-limited providers since it's fewer chat completions.
            baseline = self._gather_baseline_context(alert_data)
            if baseline:
                self._store_evidence(
                    investigation_id,
                    source_type="baseline_context",
                    source_id=None,
                    data=baseline,
                    notes="Auto-collected before investigation started (asset + recent history for this agent).",
                )

            result = self._run_loop(investigation_id, alert_data, baseline)

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

    # ── Baseline context (pre-fetched, not an LLM tool call) ─────────

    def _gather_baseline_context(self, alert_data: dict[str, Any]) -> dict[str, Any]:
        """Fetch the context almost every investigation ends up asking for
        anyway — the asset record and recent alert history for the same
        agent — using the already-registered tools directly (no LLM call).

        Best-effort: any failure here just means a smaller baseline, never
        aborts the investigation.
        """
        baseline: dict[str, Any] = {}
        agent_id = (alert_data.get("agent") or {}).get("id")
        if not agent_id:
            return baseline

        asset_tool = self._tools.get("search_assets")
        if asset_tool is not None:
            try:
                asset_result = asset_tool.execute(wazuh_agent_id=agent_id)
                assets = asset_result.get("assets") if isinstance(asset_result, dict) else None
                if assets:
                    baseline["asset"] = assets[0]
            except Exception as e:
                logger.warning("Baseline context — asset lookup failed: %s", e)

        alerts_tool = self._tools.get("search_alerts")
        if alerts_tool is not None:
            try:
                current_id = alert_data.get("id")
                recent = alerts_tool.execute(agent_id=agent_id, limit=10)
                recent_alerts = recent.get("alerts") if isinstance(recent, dict) else None
                if recent_alerts:
                    # Drop the triggering alert itself — it's already shown
                    # in full above this.
                    recent_alerts = [a for a in recent_alerts if a.get("id") != current_id]
                if recent_alerts:
                    baseline["recent_alerts_same_agent"] = recent_alerts[:9]
            except Exception as e:
                logger.warning("Baseline context — recent alerts lookup failed: %s", e)

        return baseline

    # ── Agentic loop ────────────────────────────────────────────────

    def _run_loop(
        self,
        investigation_id: str,
        alert_data: dict[str, Any],
        baseline: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """The core tool-calling loop."""

        baseline_block = ""
        if baseline:
            baseline_block = (
                "\n\nBaseline context (already collected for you — an asset "
                "record and recent alert history for this same agent, if "
                "any exist; don't re-fetch these unless you need a "
                "different agent/IP/rule/time range):\n\n"
                f"```json\n{_bounded_json(baseline, limit=4000)}\n```"
            )

        # Build initial messages.
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Investigate this security alert:\n\n"
                    f"```json\n{json.dumps(alert_data, indent=2, default=str)}\n```"
                    f"{baseline_block}\n\n"
                    "Use your tools to gather any additional context not "
                    "already covered above, then provide your verdict."
                ),
            },
        ]

        # Tracks (tool_name, sorted-args) signatures already called this
        # investigation, so an exact repeat can be short-circuited instead
        # of hitting Wazuh/MySQL again and burning another step for no new
        # information — the exact pattern of a model re-querying the same
        # thing with slightly reworded arguments.
        seen_calls: dict[tuple[str, str], Any] = {}

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
                    investigation_id, tc.name, tc.arguments, reasoning=reasoning,
                    seen_calls=seen_calls,
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
                return self._force_final_verdict(investigation_id, messages, tool_schemas)

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
        tool_schemas: Optional[list[dict]] = None,
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
        # Still pass the tool schemas alongside tool_choice="none" (rather
        # than omitting tools altogether) — some providers (Groq's gpt-oss
        # models) are more likely to actually honour "don't call a tool"
        # when they can see what tool_choice="none" is refusing, versus
        # being asked to refuse tools they were never shown for this call.
        try:
            response = self._llm.chat(messages, tools=tool_schemas, tool_choice="none")
        except ToolChoiceViolationError as e:
            # It tried to call a tool anyway and the provider rejected the
            # whole response instead of degrading to plain text. Rather
            # than failing the investigation outright over what's really
            # just "it ran out of budget while still wanting to dig
            # further", record that honestly as a NEEDS_REVIEW verdict.
            logger.warning(
                "Investigation %s — model attempted a tool call (%s) after "
                "being told not to; provider rejected it (%s). Falling "
                "back to a NEEDS_REVIEW verdict instead of failing.",
                investigation_id, e.attempted_tool_call, e,
            )
            attempted_note = ""
            if e.attempted_tool_call:
                attempted_note = (
                    f" It was still trying to call `{e.attempted_tool_call.get('name', 'a tool')}` "
                    f"with arguments {json.dumps(e.attempted_tool_call.get('arguments', {}), default=str)} "
                    "when it ran out of investigation budget."
                )
            return {
                "verdict": "NEEDS_REVIEW",
                "confidence": 0.0,
                "summary": (
                    "The investigation reached its step/context limit while "
                    "the AI was still trying to gather more information, and "
                    "it could not be forced to produce a plain-text final "
                    "answer instead."
                ),
                "details": (
                    "Automated fallback verdict — the model kept attempting "
                    "tool calls even after being told to stop and answer "
                    "with what it had so far." + attempted_note
                ),
            }
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
        seen_calls: Optional[dict[tuple[str, str], Any]] = None,
    ) -> Any:
        """Execute a tool and record the action.

        If ``seen_calls`` is given and this exact (tool, arguments) pair was
        already called earlier in the same investigation, skip re-querying
        Wazuh/MySQL and hand back the cached result with a note — this is
        the deterministic backstop for a model that repeats a search with
        slightly reworded arguments instead of concluding.
        """
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

        signature = (tool_name, json.dumps(arguments, sort_keys=True, default=str))
        if seen_calls is not None and signature in seen_calls:
            logger.info("  → %s(%s) is a duplicate of an earlier call this investigation — reusing result", tool_name, arguments)
            note = (
                "You already called this exact tool with these exact arguments "
                "earlier in this investigation — no new information here. "
                "Reusing the previous result below. Try a genuinely different "
                "tool or parameters, or provide your final verdict."
            )
            cached = seen_calls[signature]
            self._record_action(
                investigation_id, tool_name,
                description=json.dumps(arguments),
                reasoning=reasoning,
                status="completed", result=f"[duplicate call — cached] {note}",
            )
            return {"note": note, "cached_result": cached}

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
            if seen_calls is not None:
                seen_calls[signature] = result
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
