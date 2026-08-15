"""
Investigation Policy — defines which Wazuh alerts should trigger investigations.

Policies are stored in MySQL and evaluated at runtime. Each policy has a
set of conditions (minimum rule level, specific rule IDs, etc.) that are
checked against incoming alerts.  When a policy matches, it signals the
Investigation Manager to create a new investigation.

Design goals:
    • Policies live in the database so they can be managed from the frontend.
    • The evaluation engine is separate from the storage layer.
    • New condition types can be added without changing the evaluation loop —
      just add a handler to _CONDITION_HANDLERS.

Usage:
    from database import Database
    from investigation_policy import PolicyEngine

    db = Database()
    engine = PolicyEngine(db)

    match = engine.evaluate(alert)   # returns the matching policy or None
"""

from __future__ import annotations

import json
from typing import Any, Optional

from database import Database, new_id


# ── Condition Handlers ──────────────────────────────────────────────────
# Each handler takes (alert, condition_value) and returns True if the
# alert satisfies that condition.  Register new condition types here.


def _check_min_level(alert: dict[str, Any], min_level: int) -> bool:
    """True if the alert's rule level >= min_level."""
    level = _nested_get(alert, "rule", "level")
    if level is None:
        return False
    return int(level) >= int(min_level)


def _check_rule_ids(alert: dict[str, Any], rule_ids: list[str]) -> bool:
    """True if the alert's rule ID is in the given list."""
    rule_id = _nested_get(alert, "rule", "id")
    if rule_id is None:
        return False
    return str(rule_id) in [str(r) for r in rule_ids]


# Map from condition key (as stored in the JSON) to its handler function.
_CONDITION_HANDLERS: dict[str, Any] = {
    "min_level": _check_min_level,
    "rule_ids":  _check_rule_ids,
}


# ── Policy Engine ─────────────────────────────────────────────────────


class PolicyEngine:
    """Loads policies from MySQL and evaluates alerts against them.

    The engine checks every enabled policy in priority order (highest
    priority first).  The first policy whose conditions ALL match the
    alert wins.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    # ── evaluation ──────────────────────────────────────────────────

    def evaluate(self, alert: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Evaluate an alert against all enabled policies.

        Returns the first matching policy as a dict, or None.
        """
        policies = self._get_enabled_policies()

        for policy in policies:
            if self._matches(alert, policy):
                return policy

        return None

    def _matches(
        self, alert: dict[str, Any], policy: dict[str, Any],
    ) -> bool:
        """Check if an alert satisfies ALL conditions of a policy."""
        conditions = policy.get("conditions", {})

        # Parse JSON string if necessary.
        if isinstance(conditions, str):
            conditions = json.loads(conditions)

        # An empty conditions dict matches nothing (safety net).
        if not conditions:
            return False

        for key, value in conditions.items():
            handler = _CONDITION_HANDLERS.get(key)
            if handler is None:
                # Unknown condition type — skip it rather than block.
                continue
            if not handler(alert, value):
                return False

        return True

    # ── database queries ────────────────────────────────────────────

    def _get_enabled_policies(self) -> list[dict[str, Any]]:
        """Load all enabled policies, ordered by priority (highest first)."""
        return self._db.fetchall(
            "SELECT * FROM investigation_policies "
            "WHERE is_enabled = TRUE "
            "ORDER BY priority DESC, created_at ASC"
        )

    # ── CRUD (for future frontend / CLI use) ────────────────────────

    def create_policy(
        self,
        name: str,
        conditions: dict[str, Any],
        *,
        description: str = "",
        is_enabled: bool = True,
        priority: int = 0,
    ) -> str:
        """Create a new investigation policy.

        Args:
            name:        Human-readable policy name (must be unique).
            conditions:  Dict of condition_key → value.
                         Supported keys: 'min_level' (int), 'rule_ids' (list[str]).
            description: Optional description.
            is_enabled:  Whether the policy is active.
            priority:    Higher number = evaluated first.

        Returns:
            The new policy's UUID.
        """
        policy_id = new_id()
        self._db.execute(
            "INSERT INTO investigation_policies "
            "(id, name, description, is_enabled, priority, conditions) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                policy_id,
                name,
                description,
                is_enabled,
                priority,
                json.dumps(conditions),
            ),
        )
        return policy_id

    def get_policy(self, policy_id: str) -> Optional[dict[str, Any]]:
        """Retrieve a single policy by ID."""
        return self._db.fetchone(
            "SELECT * FROM investigation_policies WHERE id = %s",
            (policy_id,),
        )

    def list_policies(
        self, *, enabled_only: bool = False,
    ) -> list[dict[str, Any]]:
        """List all policies, optionally filtered to enabled ones."""
        if enabled_only:
            return self._db.fetchall(
                "SELECT * FROM investigation_policies "
                "WHERE is_enabled = TRUE "
                "ORDER BY priority DESC, created_at ASC"
            )
        return self._db.fetchall(
            "SELECT * FROM investigation_policies "
            "ORDER BY priority DESC, created_at ASC"
        )

    def update_policy(
        self,
        policy_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_enabled: Optional[bool] = None,
        priority: Optional[int] = None,
        conditions: Optional[dict[str, Any]] = None,
    ) -> int:
        """Update one or more fields of an existing policy.

        Returns the number of affected rows (0 if not found).
        """
        fields: list[str] = []
        values: list[Any] = []

        if name is not None:
            fields.append("name = %s")
            values.append(name)
        if description is not None:
            fields.append("description = %s")
            values.append(description)
        if is_enabled is not None:
            fields.append("is_enabled = %s")
            values.append(is_enabled)
        if priority is not None:
            fields.append("priority = %s")
            values.append(priority)
        if conditions is not None:
            fields.append("conditions = %s")
            values.append(json.dumps(conditions))

        if not fields:
            return 0

        values.append(policy_id)
        return self._db.execute(
            f"UPDATE investigation_policies SET {', '.join(fields)} "
            f"WHERE id = %s",
            tuple(values),
        )

    def delete_policy(self, policy_id: str) -> int:
        """Delete a policy by ID.  Returns rows affected (0 or 1)."""
        return self._db.execute(
            "DELETE FROM investigation_policies WHERE id = %s",
            (policy_id,),
        )

    def seed_defaults(self) -> None:
        """Insert sensible default policies if the table is empty.

        Idempotent — does nothing when policies already exist.
        """
        existing = self._db.fetchone(
            "SELECT COUNT(*) AS cnt FROM investigation_policies"
        )
        if existing and existing["cnt"] > 0:
            return

        self.create_policy(
            name="High-severity alerts",
            description="Investigate any alert with rule level >= 10.",
            conditions={"min_level": 10},
            priority=10,
        )
        self.create_policy(
            name="Critical-severity alerts",
            description="Investigate any alert with rule level >= 13.",
            conditions={"min_level": 13},
            priority=20,
        )


# ── tiny utility ────────────────────────────────────────────────────────

def _nested_get(data: dict, *keys: str) -> Any:
    """Safely traverse nested dicts.  Returns None on any missing key."""
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)  # type: ignore[assignment]
        if data is None:
            return None
    return data
