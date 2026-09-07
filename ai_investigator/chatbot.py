"""
Security Chatbot — free-form conversational assistant for the platform.

Shares the exact same read-only tool set as the AI Investigator (search
Wazuh alerts, look up investigations/evidence/analysis, search assets) via
``ai_investigator.tools.build_default_tools`` — see there for why the
``users`` table is deliberately unreachable: there is no tool for it, so
nothing here can read or search account data no matter what's asked.

Unlike AIInvestigator, a chat isn't bound to one alert with a verdict at
the end — it's an open-ended, multi-turn conversation. Each turn only
persists the user's message and the assistant's final answer; the
tool-calling round trip within a turn is rebuilt fresh from that stored
history and thrown away once the turn ends. That keeps conversation size
(and therefore LLM request cost) bounded no matter how many turns a
session accumulates — the same class of problem that made investigations
blow past provider size/rate limits when the whole tool transcript was
kept forever.

Usage:
    from ai_investigator.chatbot import SecurityChatbot

    chatbot = SecurityChatbot(llm=llm, db=db, alert_receiver=receiver)
    session = chatbot.create_session()
    reply = chatbot.send_message(session["id"], "any alerts on pop-os today?")
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from database import Database, new_id
from alert_receiver import AlertReceiver
from ai_investigator.llm.base import LLMProvider, ToolChoiceViolationError
from ai_investigator.tools import build_default_tools, Tool

logger = logging.getLogger("ai_investigator.chat")

# Kept small for the same reason as the investigator's limits: the system
# prompt + tool schemas already cost a fair chunk of a small free-tier
# tokens-per-minute budget before a single word of conversation is sent.
MAX_STEPS = 6
MAX_TOOL_RESULT_CHARS = 800
MAX_TURN_CHARS = 8_000

SYSTEM_PROMPT = """\
You are a security assistant embedded in a Security Investigation Platform. \
Analysts chat with you to explore Wazuh alerts, investigations, evidence, \
analyses, and assets.

## Tools

Use your tools whenever a question needs real data — never guess or \
fabricate alert or investigation content. You do not have access to user \
account data and never will; say so plainly if asked.

If asked about an IP address, or a suspicious external IP comes up while \
investigating an alert, use `check_ip_reputation` (skip it for private/ \
internal IPs — it only covers public addresses).

If a tool call returns an error, that means the call failed — it does NOT \
mean the thing you searched for doesn't exist. Report the error itself \
(and retry with corrected arguments if the fix is obvious, e.g. a required \
field was missing) rather than concluding "none found" or "not indexed" \
from it. Only state something doesn't exist when a tool call actually \
succeeded and came back with a zero count.

## Style

- Be direct and concise — analysts are experienced, skip the preamble.
- Cite what you found (rule IDs, agent names, investigation IDs) so your \
answer is checkable against the platform.
- If your tools can't answer something, say so instead of speculating.
- Reach a useful answer in a few tool calls. Don't repeat a near-identical \
search hoping for a different result — duplicate calls are blocked and \
just return the same cached result. Batch independent lookups together \
instead of one tool call per turn.
"""


def _bounded_json(obj: Any, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
    """Serialise ``obj`` to JSON, truncating if it exceeds ``limit`` chars."""
    text = json.dumps(obj, default=str)
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [truncated, {len(text)} chars total]"


def _conversation_size(messages: list[dict[str, Any]]) -> int:
    return len(json.dumps(messages, default=str))


class SecurityChatbot:
    """Multi-turn chat assistant backed by the same tools as AIInvestigator."""

    def __init__(
        self,
        llm: LLMProvider,
        db: Database,
        alert_receiver: Optional[AlertReceiver] = None,
        max_steps: int = MAX_STEPS,
    ) -> None:
        self._llm = llm
        self._db = db
        self._max_steps = max_steps
        self._tools: dict[str, Tool] = build_default_tools(db, alert_receiver)

    # ── Sessions ─────────────────────────────────────────────────────

    def create_session(self, title: Optional[str] = None) -> dict[str, Any]:
        session_id = new_id()
        self._db.execute(
            "INSERT INTO chat_sessions (id, title) VALUES (%s, %s)",
            (session_id, title or "New chat"),
        )
        row = self.get_session(session_id)
        assert row is not None
        return row

    def list_sessions(self) -> list[dict[str, Any]]:
        return self._db.fetchall("SELECT * FROM chat_sessions ORDER BY updated_at DESC")

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        return self._db.fetchone("SELECT * FROM chat_sessions WHERE id = %s", (session_id,))

    def rename_session(self, session_id: str, title: str) -> None:
        self._db.execute(
            "UPDATE chat_sessions SET title = %s WHERE id = %s", (title, session_id)
        )

    def delete_session(self, session_id: str) -> None:
        self._db.execute("DELETE FROM chat_messages WHERE session_id = %s", (session_id,))
        self._db.execute("DELETE FROM chat_sessions WHERE id = %s", (session_id,))

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        return self._db.fetchall(
            "SELECT * FROM chat_messages WHERE session_id = %s ORDER BY created_at",
            (session_id,),
        )

    # ── Sending a message ────────────────────────────────────────────

    def send_message(self, session_id: str, user_text: str) -> dict[str, Any]:
        """Post a user message, run the tool-calling loop, persist and
        return the assistant's reply row."""
        history = self.list_messages(session_id)

        # Auto-title the session from the first message, same idea as any
        # chat UI — only if it's still on the untouched default.
        if not history:
            session = self.get_session(session_id)
            if session and session["title"] == "New chat":
                title = user_text.strip().splitlines()[0][:60]
                if title:
                    self.rename_session(session_id, title)

        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for m in history:
            messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": user_text})

        # Persist the user's message right away — even if the assistant's
        # turn fails below, the question itself isn't lost.
        self._db.execute(
            "INSERT INTO chat_messages (id, session_id, role, content) "
            "VALUES (%s, %s, 'user', %s)",
            (new_id(), session_id, user_text),
        )
        self._touch_session(session_id)

        tool_schemas = [tool.schema() for tool in self._tools.values()]
        seen_calls: dict[tuple[str, str], Any] = {}
        trace: list[dict[str, Any]] = []

        try:
            for _step in range(self._max_steps):
                response = self._llm.chat(messages, tools=tool_schemas)

                if not response.has_tool_calls:
                    final_text = (response.content or "").strip()
                    if not final_text:
                        final_text = (
                            "I wasn't able to produce an answer for that "
                            "(the model returned an empty response)."
                        )
                    return self._store_reply(
                        session_id, final_text, self._distinct_reasoning(response, final_text), trace
                    )

                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": response.content or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                        }
                        for tc in response.tool_calls
                    ],
                }
                messages.append(assistant_msg)

                for tc in response.tool_calls:
                    result = self._execute_tool(tc.name, tc.arguments, seen_calls, trace)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": _bounded_json(result),
                    })

                if _conversation_size(messages) >= MAX_TURN_CHARS:
                    return self._force_final(session_id, messages, tool_schemas, trace)

            return self._force_final(session_id, messages, tool_schemas, trace)

        except ToolChoiceViolationError as e:
            logger.warning("Chat session %s — tool choice violation: %s", session_id, e)
            return self._store_reply(
                session_id,
                "I ran out of turns while still trying to look something up "
                "and couldn't wrap up cleanly. Try rephrasing, or ask a more "
                "specific question.",
                None, trace,
            )
        except Exception as e:
            logger.error("Chat session %s failed: %s", session_id, e)
            return self._store_reply(
                session_id, f"Something went wrong answering that: {e}", None, trace,
            )

    def _force_final(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
        tool_schemas: list[dict],
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Ask for a final answer, no more tool calls allowed."""
        messages.append({
            "role": "user",
            "content": (
                "Wrap up now with your best answer based on what you've "
                "found so far — no more tool calls."
            ),
        })
        try:
            # Pass the tool schemas alongside tool_choice="none" rather than
            # omitting tools altogether — some providers (Groq's gpt-oss
            # models) are more likely to actually honour "don't call a
            # tool" when they can see what's being refused. See
            # investigator.py's _force_final_verdict for the same fix.
            response = self._llm.chat(messages, tools=tool_schemas, tool_choice="none")
        except ToolChoiceViolationError:
            return self._store_reply(
                session_id,
                "I gathered some information but ran out of turns before I "
                "could finish. Try asking a narrower question.",
                None, trace,
            )
        final_text = (response.content or "").strip() or (
            "I wasn't able to produce a final answer for that."
        )
        return self._store_reply(session_id, final_text, self._distinct_reasoning(response, final_text), trace)

    @staticmethod
    def _distinct_reasoning(response, final_text: str) -> Optional[str]:
        """The model's internal chain-of-thought, if the provider returned
        one *and* it says something the final answer doesn't already say.

        Deliberately uses the raw ``reasoning`` field, not
        ``reasoning_text`` — that property falls back to ``content`` when
        there's no separate reasoning, which here would just duplicate the
        answer itself as its own "reasoning".
        """
        reasoning = (response.reasoning or "").strip()
        if not reasoning or reasoning == final_text.strip():
            return None
        return reasoning

    def _execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        seen_calls: dict[tuple[str, str], Any],
        trace: list[dict[str, Any]],
    ) -> Any:
        tool = self._tools.get(tool_name)
        if tool is None:
            logger.warning("  → unknown tool requested: %s(%s)", tool_name, arguments)
            result = {"error": f"Unknown tool: {tool_name}"}
            trace.append({"tool": tool_name, "arguments": arguments, "result_summary": result["error"]})
            return result

        signature = (tool_name, json.dumps(arguments, sort_keys=True, default=str))
        if signature in seen_calls:
            logger.info("  → %s(%s) is a duplicate call this turn — reusing result", tool_name, arguments)
            note = "Duplicate of an earlier call this turn — reusing cached result."
            trace.append({"tool": tool_name, "arguments": arguments, "result_summary": note})
            return {"note": note, "cached_result": seen_calls[signature]}

        logger.info("  → calling %s(%s)", tool_name, arguments)
        try:
            result = tool.execute(**arguments)
        except Exception as e:
            logger.error("  → %s failed: %s", tool_name, e)
            result = {"error": f"Tool error: {e}"}

        seen_calls[signature] = result
        result_str = json.dumps(result, default=str)
        trace.append({
            "tool": tool_name,
            "arguments": arguments,
            "result_summary": result_str[:500] + ("..." if len(result_str) > 500 else ""),
        })
        return result

    def _store_reply(
        self,
        session_id: str,
        content: str,
        reasoning: Optional[str],
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        message_id = new_id()
        self._db.execute(
            "INSERT INTO chat_messages (id, session_id, role, content, reasoning, tool_trace) "
            "VALUES (%s, %s, 'assistant', %s, %s, %s)",
            (
                message_id, session_id, content, reasoning,
                json.dumps(trace, default=str) if trace else None,
            ),
        )
        self._touch_session(session_id)
        row = self._db.fetchone("SELECT * FROM chat_messages WHERE id = %s", (message_id,))
        assert row is not None
        return row

    def _touch_session(self, session_id: str) -> None:
        self._db.execute(
            "UPDATE chat_sessions SET updated_at = NOW() WHERE id = %s", (session_id,)
        )
