"""
Examples — how to use the Context Collector.

Before running, make sure your .env file has valid Wazuh Indexer credentials.

    source venv/bin/activate
    python context_examples.py
"""

import json
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from alert_receiver import AlertReceiver
from context_collector import ContextCollector, WazuhAlertCollector

# ── Load config from .env ───────────────────────────────────────────────
load_dotenv()

receiver = AlertReceiver(
    host=os.getenv("WAZUH_INDEXER_HOST", "localhost"),
    port=int(os.getenv("WAZUH_INDEXER_PORT", "9200")),
    username=os.getenv("WAZUH_INDEXER_USERNAME", "admin"),
    password=os.getenv("WAZUH_INDEXER_PASSWORD", "admin"),
    verify_ssl=os.getenv("WAZUH_INDEXER_VERIFY_SSL", "false").lower() == "true",
)


def print_context(title: str, context: dict) -> None:
    """Pretty-print a context result."""
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")

    # Current alert summary
    alert = context["current_alert"]
    print(f"\n  Current alert:")
    print(f"    Timestamp : {alert.get('timestamp', '?')}")
    print(f"    Agent     : {alert.get('agent', {}).get('id', '?')} "
          f"({alert.get('agent', {}).get('name', '?')})")
    print(f"    Rule      : {alert.get('rule', {}).get('id', '?')} "
          f"(level {alert.get('rule', {}).get('level', '?')})")
    print(f"    Desc      : {alert.get('rule', {}).get('description', '?')}")

    src_ip = alert.get("data", {}).get("srcip")
    if src_ip:
        print(f"    Source IP : {src_ip}")

    src_user = alert.get("data", {}).get("srcuser")
    if src_user:
        print(f"    Src User  : {src_user}")

    # Related alerts from the wazuh_alerts collector
    wazuh_ctx = context.get("wazuh_alerts", {})
    time_window = wazuh_ctx.get("time_window", {})
    print(f"\n  Time window : {time_window.get('from', '?')} → {time_window.get('to', '?')}")

    for key, alerts in wazuh_ctx.items():
        if key == "time_window" or not isinstance(alerts, list):
            continue
        print(f"\n  {key}: {len(alerts)} related alert(s)")
        for a in alerts[:3]:  # Show first 3 per category
            print(f"    • {a.get('timestamp', '?')} | "
                  f"Rule {a.get('rule', {}).get('id', '?')} "
                  f"(lvl {a.get('rule', {}).get('level', '?')}) | "
                  f"{a.get('rule', {}).get('description', '?')}")
        if len(alerts) > 3:
            print(f"    ... and {len(alerts) - 3} more")


# ── Set up the Context Collector ────────────────────────────────────────

context_collector = ContextCollector()
context_collector.add_collector(WazuhAlertCollector(receiver, window_minutes=60))


# ── Example 1: Pick the most recent alert and collect context ───────────

print("\n▶ Fetching the most recent alert to use as the 'current alert'...")
recent = receiver.get_alerts(limit=1)

if recent:
    current_alert = recent[0]
    context = context_collector.collect(current_alert)
    print_context("Example 1 — Context for the most recent alert", context)
else:
    print("  No alerts found in the Wazuh Indexer.")


# ── Example 2: Pick a high-severity alert and collect context ───────────

# print("\n\n▶ Fetching a recent high-severity alert (level ≥ 10)...")
# high_sev = receiver.get_alerts(min_level=10, limit=1)
# if high_sev:
#     current_alert = high_sev[0]
#     context = context_collector.collect(current_alert)
#     print_context("Example 2 — Context for a high-severity alert", context)
# else:
#     print("  No high-severity alerts found.")


# ── Example 3: Custom time window (last 24 hours, wider search) ─────────

# print("\n\n▶ Using a wider time window (24 hours)...")
# wide_collector = ContextCollector()
# wide_collector.add_collector(
#     WazuhAlertCollector(receiver, window_minutes=1440)  # 24 hours
# )
# recent = receiver.get_alerts(limit=1)
# if recent:
#     current_alert = recent[0]
#     context = wide_collector.collect(current_alert)
#     print_context("Example 3 — Context with 24-hour window", context)
# else:
#     print("  No alerts found.")


# ── Example 4: Print the full context as JSON ──────────────────────────

# print("\n\n▶ Full context as JSON (for the most recent alert)...")
# recent = receiver.get_alerts(limit=1)
# if recent:
#     current_alert = recent[0]
#     context = context_collector.collect(current_alert)
#     # Just show the structure (truncate alert bodies for readability)
#     summary = {
#         "current_alert_id": current_alert.get("id"),
#         "current_alert_rule": current_alert.get("rule", {}).get("description"),
#         "wazuh_alerts_keys": list(context.get("wazuh_alerts", {}).keys()),
#         "total_related": sum(
#             len(v) for v in context.get("wazuh_alerts", {}).values()
#             if isinstance(v, list)
#         ),
#     }
#     print(json.dumps(summary, indent=2))
# else:
#     print("  No alerts found.")
