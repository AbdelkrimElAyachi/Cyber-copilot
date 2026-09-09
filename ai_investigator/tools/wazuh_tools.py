"""Wazuh Indexer tools for the AI Investigator."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from alert_receiver import AlertReceiver
from .base import Tool


def _summarise_alert(alert: dict[str, Any]) -> dict[str, Any]:
    """Extract key fields from an alert to keep token usage reasonable."""
    rule = alert.get("rule", {})
    agent = alert.get("agent", {})
    data = alert.get("data", {})
    full_log = alert.get("full_log", "")

    return {
        "id": alert.get("id"),
        "timestamp": alert.get("timestamp"),
        "agent_id": agent.get("id"),
        "agent_name": agent.get("name"),
        "agent_ip": agent.get("ip"),
        "rule_id": rule.get("id"),
        "rule_level": rule.get("level"),
        "rule_description": rule.get("description"),
        "rule_groups": rule.get("groups"),
        "src_ip": data.get("srcip"),
        "dst_ip": data.get("dstip"),
        "src_user": data.get("srcuser"),
        "dst_user": data.get("dstuser"),
        "location": alert.get("location"),
        "full_log": full_log[:500] if full_log else None,
    }


class SearchAlertsTool(Tool):
    """Search Wazuh alerts with filters."""

    def __init__(self, receiver: AlertReceiver) -> None:
        self._receiver = receiver

    @property
    def name(self) -> str:
        return "search_alerts"

    @property
    def description(self) -> str:
        return (
            "Search Wazuh security alerts. Use filters to narrow results. "
            "Returns summarised alert data. Use get_alert_details for full data."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text search across alert logs.",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Wazuh agent ID (e.g. '001').",
                },
                "agent_name": {
                    "type": "string",
                    "description": "Agent hostname.",
                },
                "rule_id": {
                    "type": "string",
                    "description": "Wazuh rule ID (e.g. '5710').",
                },
                "rule_level_min": {
                    "type": "integer",
                    "description": "Minimum rule level (1-16).",
                },
                "source_ip": {
                    "type": "string",
                    "description": "Source IP address.",
                },
                "time_from": {
                    "type": "string",
                    "description": "Start time in ISO format (e.g. '2026-08-20T00:00:00').",
                },
                "time_to": {
                    "type": "string",
                    "description": "End time in ISO format.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 20, max 50).",
                },
            },
            "required": [],
        }

    def execute(self, **kwargs: Any) -> Any:
        try:
            # Parse parameters.
            from_time = None
            to_time = None
            if kwargs.get("time_from"):
                from_time = datetime.fromisoformat(kwargs["time_from"])
            if kwargs.get("time_to"):
                to_time = datetime.fromisoformat(kwargs["time_to"])

            limit = min(kwargs.get("limit", 20), 50)

            alerts = self._receiver.get_alerts(
                search_text=kwargs.get("query"),
                agent_id=kwargs.get("agent_id"),
                agent_name=kwargs.get("agent_name"),
                rule_id=kwargs.get("rule_id"),
                min_level=kwargs.get("rule_level_min"),
                source_ip=kwargs.get("source_ip"),
                from_time=from_time,
                to_time=to_time,
                limit=limit,
            )

            return {
                "count": len(alerts),
                "alerts": [_summarise_alert(a) for a in alerts],
            }
        except Exception as e:
            return {"error": str(e), "count": 0, "alerts": []}


class CountAlertsTool(Tool):
    """Count Wazuh alerts matching filters, without fetching them.

    ``search_alerts`` caps results at 50 and its "count" is just how many
    of those it returned — not the true total. For "how many alerts..."
    questions, this calls the Indexer's own count API instead, which is
    exact and isn't limited by any result-size cap.
    """

    def __init__(self, receiver: AlertReceiver) -> None:
        self._receiver = receiver

    @property
    def name(self) -> str:
        return "count_alerts"

    @property
    def description(self) -> str:
        return (
            "Get the exact total number of Wazuh alerts matching optional "
            "filters — use this for any 'how many alerts...' question "
            "instead of counting search_alerts results, which are capped "
            "at 50 and don't reflect the true total. Omit all filters to "
            "count every alert in the index."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text search across alert logs.",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Wazuh agent ID (e.g. '001').",
                },
                "agent_name": {
                    "type": "string",
                    "description": "Agent hostname.",
                },
                "rule_id": {
                    "type": "string",
                    "description": "Wazuh rule ID (e.g. '5710').",
                },
                "rule_level_min": {
                    "type": "integer",
                    "description": "Minimum rule level (1-16).",
                },
                "source_ip": {
                    "type": "string",
                    "description": "Source IP address.",
                },
                "time_from": {
                    "type": "string",
                    "description": "Start time in ISO format (e.g. '2026-08-20T00:00:00').",
                },
                "time_to": {
                    "type": "string",
                    "description": "End time in ISO format.",
                },
            },
            "required": [],
        }

    def execute(self, **kwargs: Any) -> Any:
        try:
            from_time = None
            to_time = None
            if kwargs.get("time_from"):
                from_time = datetime.fromisoformat(kwargs["time_from"])
            if kwargs.get("time_to"):
                to_time = datetime.fromisoformat(kwargs["time_to"])

            total = self._receiver.count_alerts(
                search_text=kwargs.get("query"),
                agent_id=kwargs.get("agent_id"),
                agent_name=kwargs.get("agent_name"),
                rule_id=kwargs.get("rule_id"),
                min_level=kwargs.get("rule_level_min"),
                source_ip=kwargs.get("source_ip"),
                from_time=from_time,
                to_time=to_time,
            )
            return {"count": total}
        except Exception as e:
            return {"error": str(e)}


class GetAlertDetailsTool(Tool):
    """Get full details of a specific Wazuh alert."""

    def __init__(self, receiver: AlertReceiver) -> None:
        self._receiver = receiver

    @property
    def name(self) -> str:
        return "get_alert_details"

    @property
    def description(self) -> str:
        return "Get the full details of a specific Wazuh alert by its ID."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "alert_id": {
                    "type": "string",
                    "description": "The Wazuh alert ID.",
                },
            },
            "required": ["alert_id"],
        }

    def execute(self, **kwargs: Any) -> Any:
        alert_id = kwargs.get("alert_id", "")
        if not alert_id:
            return {"error": "alert_id is required"}
        try:
            alert = self._receiver.get_alert_by_id(alert_id)
            if alert is None:
                return {"error": f"Alert {alert_id} not found"}
            return alert
        except Exception as e:
            return {"error": str(e)}
