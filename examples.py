"""
Examples — how to use the AlertReceiver.

Before running, copy .env.example to .env and fill in your Wazuh Indexer
credentials:

    cp .env.example .env
    nano .env

Then run this script:

    source venv/bin/activate
    python examples.py
"""

import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from alert_receiver import AlertReceiver

# ── Load config from .env ───────────────────────────────────────────────
load_dotenv()

receiver = AlertReceiver(
    host=os.getenv("WAZUH_INDEXER_HOST", "localhost"),
    port=int(os.getenv("WAZUH_INDEXER_PORT", "9200")),
    username=os.getenv("WAZUH_INDEXER_USERNAME", "admin"),
    password=os.getenv("WAZUH_INDEXER_PASSWORD", "admin"),
    verify_ssl=os.getenv("WAZUH_INDEXER_VERIFY_SSL", "false").lower() == "true",
)


def print_alerts(title: str, alerts: list[dict]) -> None:
    """Pretty-print a list of alerts."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"  Found {len(alerts)} alert(s)")
    print(f"{'=' * 60}")
    for alert in alerts[:5]:  # Show first 5 to keep output readable
        print(f"  {alert.get('timestamp', '?')} \n"
              f"  Agent {alert.get('agent', {}).get('id', '?')} \n"
              f"  Rule {alert.get('rule', {}).get('id', '?')}\n"
              f"  level {alert.get('rule', {}).get('level', '?')})\n"
              f"  — {alert.get('rule', {}).get('description', '?')}\n")
    if len(alerts) > 5:
        print(f"  ... and {len(alerts) - 5} more")


# ── 1. Get the latest 100 alerts ────────────────────────────────────────

# alerts = receiver.get_alerts(limit=1)
# print_alerts("1. Latest 100 alerts", alerts)


# ── 2. Get alerts from a specific time range ────────────────────────────

now = datetime.now(tz=timezone.utc)
one_hour_ago = now - timedelta(hours=1)
alerts = receiver.get_alerts(
    from_time=one_hour_ago,
    to_time=now,
    limit=2,
)
print_alerts("Alerts from the last hour : ", alerts)


# ── 3. Get alerts from a specific agent ─────────────────────────────────

# alerts = receiver.get_alerts(agent_id="000", limit=1)
# print_alerts("3. Alerts from agent 000", alerts)


# ── 4. Get alerts with a minimum rule level ─────────────────────────────

# alerts = receiver.get_alerts(min_level=8, limit=1)
# print_alerts("High-severity alerts (level >= 10)", alerts)


# ── 5. Combine multiple filters ────────────────────────────────────────

alerts = receiver.get_alerts(
    agent_id="000",
    min_level=8,
    from_time=now - timedelta(days=10),
    to_time=now,
    limit=1,
)
print_alerts("5. Agent 001 + level >= 8 + last 24 hours", alerts)


# ── Bonus: count how many alerts match a filter ────────────────────────

# total = receiver.count_alerts(min_level=12)
# print(f"\n  Total alerts with level >= 12: {total}")


# ── Bonus: filter by rule ID ───────────────────────────────────────────

# alerts = receiver.get_alerts(rule_id="5710", limit=10)
# print_alerts("Bonus: Alerts for rule 5710 (sshd login attempts)", alerts)


# ── Bonus: filter by source IP ─────────────────────────────────────────

# alerts = receiver.get_alerts(source_ip="10.0.0.5", min_level=5, limit=10)
# print_alerts("Bonus: Alerts from source IP 10.0.0.5 (level >= 5)", alerts)
