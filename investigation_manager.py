"""
Investigation Manager — decides whether to create an investigation for a
Wazuh alert, and creates it when appropriate.

This is the glue between the Alert Receiver, the Policy Engine, and the
database.  It does NOT contain any policy logic itself — that belongs in
the PolicyEngine.

Flow:
    Wazuh Alert
        ↓
    InvestigationManager.process_alert(alert)
        ↓
    1. Extract the alert's unique ID.
    2. Check for a duplicate investigation (same alert_id).
    3. Evaluate the alert against enabled policies (via PolicyEngine).
    4. If a policy matches → create investigation with QUEUED status.
        ↓
    Returns a ProcessResult with what happened and why.

Usage:
    from database import Database
    from investigation_policy import PolicyEngine
    from investigation_manager import InvestigationManager

    db = Database()
    db.init_tables()
    engine = PolicyEngine(db)
    manager = InvestigationManager(db, engine)

    result = manager.process_alert(alert)
    print(result)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from database import Database, new_id
from investigation_policy import PolicyEngine


# ── Result types ────────────────────────────────────────────────────────


class Outcome(Enum):
    """What happened when the manager processed an alert."""

    CREATED = "created"              # New investigation was created.
    DUPLICATE = "duplicate"          # Investigation already exists for this alert.
    NO_POLICY_MATCH = "no_match"     # No enabled policy matched the alert.
    SKIPPED = "skipped"              # Alert lacked an ID — cannot track it.


@dataclass
class ProcessResult:
    """Outcome of processing a single alert."""

    outcome: Outcome
    alert_id: Optional[str] = None
    investigation_id: Optional[str] = None
    policy_id: Optional[str] = None
    policy_name: Optional[str] = None
    reason: str = ""

    def __str__(self) -> str:
        parts = [f"[InvestigationManager] {self.outcome.value}"]
        if self.alert_id:
            parts.append(f"alert={self.alert_id}")
        if self.investigation_id:
            parts.append(f"investigation={self.investigation_id}")
        if self.policy_name:
            parts.append(f"policy='{self.policy_name}'")
        if self.reason:
            parts.append(f"({self.reason})")
        return "  ".join(parts)


# ── Investigation Manager ──────────────────────────────────────────────


class InvestigationManager:
    """Processes Wazuh alerts and creates investigations when policies match.

    This class is intentionally thin: it orchestrates the decision but
    delegates the actual matching logic to the PolicyEngine.
    """

    def __init__(self, db: Database, policy_engine: PolicyEngine) -> None:
        self._db = db
        self._policy_engine = policy_engine

    # ── public API ──────────────────────────────────────────────────

    def process_alert(self, alert: dict[str, Any]) -> ProcessResult:
        """Decide whether to investigate an alert, and act on that decision.

        Steps:
            1. Extract the alert's unique ID.
            2. Reject if no ID (we can't deduplicate without one).
            3. Skip if an investigation already exists for this alert.
            4. Evaluate enabled policies.
            5. Create the investigation if a policy matches.

        Returns:
            A ProcessResult describing what happened.
        """
        # ── 1. Extract alert identity ──────────────────────────────
        alert_id = self._extract_alert_id(alert)

        if not alert_id:
            return ProcessResult(
                outcome=Outcome.SKIPPED,
                reason="Alert has no ID field — cannot track.",
            )

        # ── 2. Duplicate check ─────────────────────────────────────
        existing = self._db.fetchone(
            "SELECT id FROM investigations WHERE alert_id = %s",
            (alert_id,),
        )
        if existing:
            return ProcessResult(
                outcome=Outcome.DUPLICATE,
                alert_id=alert_id,
                investigation_id=existing["id"],
                reason="Investigation already exists for this alert.",
            )

        # ── 3. Policy evaluation ───────────────────────────────────
        policy = self._policy_engine.evaluate(alert)

        if policy is None:
            return ProcessResult(
                outcome=Outcome.NO_POLICY_MATCH,
                alert_id=alert_id,
                reason="No enabled policy matched this alert.",
            )

        # ── 4. Create investigation ────────────────────────────────
        investigation_id = self._create_investigation(alert, alert_id, policy)

        return ProcessResult(
            outcome=Outcome.CREATED,
            alert_id=alert_id,
            investigation_id=investigation_id,
            policy_id=policy["id"],
            policy_name=policy["name"],
            reason="Policy conditions matched.",
        )

    def process_alerts(self, alerts: list[dict[str, Any]]) -> list[ProcessResult]:
        """Process a batch of alerts.  Returns one result per alert."""
        return [self.process_alert(a) for a in alerts]

    # ── private helpers ─────────────────────────────────────────────

    @staticmethod
    def _extract_alert_id(alert: dict[str, Any]) -> Optional[str]:
        """Pull a unique identifier out of the alert.

        Wazuh alerts have an 'id' field at the top level.
        """
        return alert.get("id")

    def _create_investigation(
        self,
        alert: dict[str, Any],
        alert_id: str,
        policy: dict[str, Any],
    ) -> str:
        """Insert a new QUEUED investigation into the database."""
        investigation_id = new_id()
        rule = alert.get("rule", {})
        agent = alert.get("agent", {})

        # Auto-create the asset if the agent doesn't exist yet.
        self._ensure_asset(alert)

        title = (
            f"[{rule.get('id', '?')}] "
            f"{rule.get('description', 'Wazuh alert investigation')}"
        )
        description = (
            f"Auto-created by policy '{policy['name']}'. "
            f"Agent: {agent.get('name', 'unknown')}. "
            f"Rule level: {rule.get('level', '?')}."
        )
        severity = _level_to_severity(rule.get("level"))

        self._db.execute(
            "INSERT INTO investigations "
            "(id, alert_id, policy_id, title, description, status, severity) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                investigation_id,
                alert_id,
                policy["id"],
                title,
                description,
                "QUEUED",
                severity,
            ),
        )

        print(
            f"[InvestigationManager] Investigation {investigation_id} created "
            f"for alert {alert_id} (policy: '{policy['name']}')"
        )
        return investigation_id

    def _ensure_asset(self, alert: dict[str, Any]) -> None:
        """Create an asset from the alert's agent if it doesn't exist yet.

        Wazuh alerts contain agent info like:
            {"agent": {"id": "001", "name": "web-server", "ip": "10.0.0.5"}}

        If no asset with that wazuh_agent_id exists, one is created.
        """
        agent = alert.get("agent", {})
        agent_id = agent.get("id")

        if not agent_id:
            return

        # Check if asset already exists for this agent.
        existing = self._db.fetchone(
            "SELECT id FROM assets WHERE wazuh_agent_id = %s",
            (str(agent_id),),
        )
        if existing:
            return

        # Extract what we can from the alert.
        hostname = agent.get("name", f"agent-{agent_id}")
        ip_address = agent.get("ip")
        os_info = alert.get("syscheck", {}).get("path", None)
        # Try to detect OS from predecoder or agent fields.
        predecoder = alert.get("predecoder", {})
        manager = alert.get("manager", {})

        asset_id = new_id()
        self._db.execute(
            "INSERT INTO assets "
            "(id, hostname, ip_address, asset_type, wazuh_agent_id, os, notes) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                asset_id,
                hostname,
                ip_address,
                "endpoint",
                str(agent_id),
                None,
                f"Auto-discovered from Wazuh agent {agent_id}.",
            ),
        )
        print(
            f"[InvestigationManager] Asset {asset_id} created "
            f"for agent {agent_id} ({hostname})"
        )


# ── helpers ─────────────────────────────────────────────────────────────


def _level_to_severity(level: Any) -> str:
    """Map a Wazuh rule level (1–16) to a human-readable severity."""
    if level is None:
        return "medium"
    level = int(level)
    if level >= 13:
        return "critical"
    if level >= 10:
        return "high"
    if level >= 7:
        return "medium"
    return "low"
