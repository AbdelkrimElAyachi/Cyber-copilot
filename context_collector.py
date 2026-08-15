"""
Context Collector — gathers contextual information around a Wazuh alert.

Architecture:

    Current Alert
          ↓
    ContextCollector            ← orchestrator
          ↓
    WazuhAlertCollector         ← first (and currently only) sub-collector
          ↓
    AlertReceiver               ← existing module — queries the Wazuh Indexer

Adding a new data source later:

    1. Subclass BaseCollector and implement collect().
    2. Register it:  context_collector.add_collector(MyNewCollector(...))

No existing code needs to change.

Usage:

    from alert_receiver import AlertReceiver
    from context_collector import ContextCollector, WazuhAlertCollector

    receiver = AlertReceiver(host="192.168.1.100", ...)
    collector = ContextCollector()
    collector.add_collector(WazuhAlertCollector(receiver))

    context = collector.collect(current_alert)
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from alert_receiver import AlertReceiver


# ── Base class ──────────────────────────────────────────────────────────


class BaseCollector(ABC):
    """Abstract base for every context sub-collector.

    Each sub-collector is responsible for one data source.  It receives the
    current alert and returns a dict of contextual information it found.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier used as key in the final context dict."""

    @abstractmethod
    def collect(self, alert: dict[str, Any]) -> dict[str, Any]:
        """Gather context for *alert* and return it as a dict."""


# ── Wazuh Alert Collector ──────────────────────────────────────────────


class WazuhAlertCollector(BaseCollector):
    """Finds related / previous Wazuh alerts for a given alert.

    Searches by:
        • same agent
        • same source IP
        • same source user
        • same rule group

    All queries are scoped to a configurable time window (default: 1 hour
    before the current alert).
    """

    name = "wazuh_alerts"

    def __init__(
        self,
        receiver: AlertReceiver,
        *,
        window_minutes: int = 60,
        max_alerts_per_query: int = 50,
    ) -> None:
        """Create a WazuhAlertCollector.

        Args:
            receiver:            An existing AlertReceiver instance.
            window_minutes:      How many minutes before the alert to search.
            max_alerts_per_query: Maximum alerts returned per sub-query.
        """
        self._receiver = receiver
        self._window_minutes = window_minutes
        self._max_alerts = max_alerts_per_query

    # ── public ──────────────────────────────────────────────────────

    def collect(self, alert: dict[str, Any]) -> dict[str, Any]:
        """Return related alerts grouped by the relationship type."""
        from_time, to_time = self._time_window(alert)
        alert_id = alert.get("id")

        results: dict[str, Any] = {
            "time_window": {
                "from": from_time.isoformat(),
                "to": to_time.isoformat(),
            },
        }

        # ── same agent ─────────────────────────────────────────────
        agent_id = _nested_get(alert, "agent", "id")
        if agent_id:
            results["by_agent"] = self._query(
                from_time, to_time, alert_id, agent_id=agent_id,
            )

        # ── same source IP ─────────────────────────────────────────
        src_ip = _nested_get(alert, "data", "srcip")
        if src_ip:
            results["by_source_ip"] = self._query(
                from_time, to_time, alert_id, source_ip=src_ip,
            )

        # ── same source user ──────────────────────────────────────
        src_user = _nested_get(alert, "data", "srcuser")
        if src_user:
            results["by_src_user"] = self._query(
                from_time, to_time, alert_id, src_user=src_user,
            )

        # ── same rule group ───────────────────────────────────────
        rule_groups = _nested_get(alert, "rule", "groups")
        if rule_groups and isinstance(rule_groups, list):
            for group in rule_groups:
                key = f"by_rule_group_{group}"
                results[key] = self._query(
                    from_time, to_time, alert_id, rule_group=group,
                )

        return results

    # ── private helpers ────────────────────────────────────────────

    def _time_window(
        self, alert: dict[str, Any],
    ) -> tuple[datetime, datetime]:
        """Compute the look-back window ending at the alert's timestamp."""
        ts_raw = alert.get("timestamp")
        if ts_raw:
            to_time = _parse_timestamp(str(ts_raw))
        else:
            to_time = datetime.now(tz=timezone.utc)

        from_time = to_time - timedelta(minutes=self._window_minutes)
        return from_time, to_time

    def _query(
        self,
        from_time: datetime,
        to_time: datetime,
        current_alert_id: Optional[str],
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """Run a single query via the AlertReceiver and exclude the current alert."""
        alerts = self._receiver.get_alerts(
            from_time=from_time,
            to_time=to_time,
            limit=self._max_alerts,
            sort_order="desc",
            **filters,
        )

        # Remove the current alert from results so we only return *related* alerts.
        if current_alert_id:
            alerts = [a for a in alerts if a.get("id") != current_alert_id]

        return alerts


# ── Context Collector (orchestrator) ───────────────────────────────────


class ContextCollector:
    """Orchestrates one or more sub-collectors to build context for an alert.

    Usage:
        collector = ContextCollector()
        collector.add_collector(WazuhAlertCollector(receiver))
        context = collector.collect(alert)
    """

    def __init__(self) -> None:
        self._collectors: list[BaseCollector] = []

    def add_collector(self, collector: BaseCollector) -> None:
        """Register a sub-collector."""
        self._collectors.append(collector)

    def collect(self, alert: dict[str, Any]) -> dict[str, Any]:
        """Run every registered sub-collector and merge the results.

        Returns:
            {
                "current_alert": <the input alert>,
                "<collector.name>": <that collector's output>,
                ...
            }
        """
        context: dict[str, Any] = {"current_alert": alert}
        for collector in self._collectors:
            context[collector.name] = collector.collect(alert)
        return context


# ── tiny utility ───────────────────────────────────────────────────────


def _nested_get(data: dict, *keys: str) -> Any:
    """Safely traverse nested dicts.  Returns None on any missing key."""
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)  # type: ignore[assignment]
        if data is None:
            return None
    return data


# Matches a timezone offset like +0100 or -0530 (no colon).
_OFFSET_RE = re.compile(r"([+-])(\d{2})(\d{2})$")


def _parse_timestamp(ts: str) -> datetime:
    """Parse a timestamp string into a timezone-aware datetime.

    Handles Wazuh's format where the UTC offset has no colon
    (e.g. ``+0100`` instead of ``+01:00``).
    """
    # Normalise "+0100" → "+01:00" so fromisoformat() can parse it.
    m = _OFFSET_RE.search(ts)
    if m:
        ts = ts[: m.start()] + f"{m.group(1)}{m.group(2)}:{m.group(3)}"

    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
