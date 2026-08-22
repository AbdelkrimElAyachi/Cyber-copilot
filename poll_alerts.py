"""
Alert Poller — periodically fetches new Wazuh alerts and creates investigations.

This script connects the AlertReceiver (Wazuh Indexer) to the
InvestigationManager (MySQL + PolicyEngine). It polls for recent alerts,
processes them through the policy engine, and creates investigations for
matching alerts.

Uses a database watermark (poller_state table) so each poll only fetches
alerts that arrived since the last successful run. The state is queryable
from the API / frontend.

Usage:
    # Activate your venv first
    python poll_alerts.py                    # single run, last 24h
    python poll_alerts.py --hours 48         # single run, last 48h
    python poll_alerts.py --loop             # continuous polling every 60s
    python poll_alerts.py --loop --interval 30  # poll every 30s
    python poll_alerts.py --reset            # clear watermark and start fresh
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv()

from alert_receiver import AlertReceiver
from database import Database, new_id
from investigation_policy import PolicyEngine
from investigation_manager import InvestigationManager


POLLER_NAME = "wazuh_alert_poller"


def _parse_timestamp(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp, handling offsets with or without colons.

    Python 3.10's fromisoformat() doesn't accept '+0100' — only '+01:00'.
    Wazuh timestamps often use the no-colon format.
    """
    import re
    # Fix timezone offset without colon: +0100 → +01:00, -0530 → -05:30
    ts = re.sub(r'([+-])(\d{2})(\d{2})$', r'\1\2:\3', ts)
    return datetime.fromisoformat(ts)


# ── Watermark (database-backed) ────────────────────────────────────────

def get_or_create_state(db: Database) -> dict:
    """Get the poller state row, creating it if it doesn't exist."""
    row = db.fetchone(
        "SELECT * FROM poller_state WHERE poller_name = %s",
        (POLLER_NAME,),
    )
    if row:
        return row

    state_id = new_id()
    db.execute(
        "INSERT INTO poller_state (id, poller_name, status) VALUES (%s, %s, %s)",
        (state_id, POLLER_NAME, "idle"),
    )
    return db.fetchone(
        "SELECT * FROM poller_state WHERE id = %s",
        (state_id,),
    )


def update_state(db: Database, **fields) -> None:
    """Update poller state fields."""
    if not fields:
        return
    set_parts = []
    values = []
    for key, val in fields.items():
        set_parts.append(f"{key} = %s")
        values.append(val)
    values.append(POLLER_NAME)
    db.execute(
        f"UPDATE poller_state SET {', '.join(set_parts)} WHERE poller_name = %s",
        tuple(values),
    )


def clear_watermark(db: Database) -> None:
    """Reset the watermark so the next run starts fresh."""
    db.execute(
        "UPDATE poller_state SET last_timestamp = NULL, total_runs = 0, "
        "total_created = 0, alerts_fetched = 0, investigations_created = 0, "
        "error_message = NULL, status = 'idle' "
        "WHERE poller_name = %s",
        (POLLER_NAME,),
    )
    print("[Poller] Watermark cleared.")


# ── Alert timestamp extraction ─────────────────────────────────────────

def get_alert_timestamp(alert: dict) -> str | None:
    """Extract the timestamp from a Wazuh alert."""
    return alert.get("timestamp")


# ── Core logic ─────────────────────────────────────────────────────────

def create_receiver() -> AlertReceiver:
    """Build an AlertReceiver from .env settings."""
    return AlertReceiver(
        host=os.getenv("WAZUH_INDEXER_HOST", "localhost"),
        port=int(os.getenv("WAZUH_INDEXER_PORT", "9200")),
        username=os.getenv("WAZUH_INDEXER_USERNAME", "admin"),
        password=os.getenv("WAZUH_INDEXER_PASSWORD", "admin"),
        verify_ssl=os.getenv("WAZUH_INDEXER_VERIFY_SSL", "false").lower() == "true",
    )


def run_once(
    db: Database,
    receiver: AlertReceiver,
    manager: InvestigationManager,
    initial_hours: int = 24,
) -> None:
    """Fetch and process only NEW alerts since the last watermark."""
    state = get_or_create_state(db)
    watermark = state.get("last_timestamp")

    # Mark as running
    update_state(db, status="running", error_message=None,
                 last_run_at=datetime.now(timezone.utc))

    if watermark:
        from_time = _parse_timestamp(watermark)
        # When --hours is passed with an existing watermark, use whichever
        # reaches further back in time.
        hours_ago = datetime.now(timezone.utc) - timedelta(hours=initial_hours)
        if hours_ago < from_time:
            from_time = hours_ago
            print(f"[Poller] --hours {initial_hours} reaches further back than watermark, "
                  f"using {from_time.isoformat()}")
        else:
            print(f"[Poller] Fetching alerts since watermark: {watermark}")
    else:
        from_time = datetime.now(timezone.utc) - timedelta(hours=initial_hours)
        print(f"[Poller] No watermark. Fetching last {initial_hours}h "
              f"(since {from_time.isoformat()})")

    try:
        alerts = receiver.get_alerts(from_time=from_time, limit=500, sort_order="asc")
    except Exception as e:
        update_state(db, status="error", error_message=str(e))
        print(f"[Poller] ERROR fetching alerts: {e}")
        return

    print(f"[Poller] Retrieved {len(alerts)} new alerts.")

    if not alerts:
        update_state(db, status="idle", alerts_fetched=0, investigations_created=0)
        print("[Poller] Nothing new to process.")
        return

    results = manager.process_alerts(alerts)

    # Find latest timestamp for watermark
    latest_ts = None
    for alert in reversed(alerts):
        ts = get_alert_timestamp(alert)
        if ts:
            latest_ts = ts
            break

    # Count results
    created = sum(1 for r in results if r.outcome.value == "created")
    duplicates = sum(1 for r in results if r.outcome.value == "duplicate")
    no_match = sum(1 for r in results if r.outcome.value == "no_match")
    skipped = sum(1 for r in results if r.outcome.value == "skipped")

    # Update state in database
    update_fields = {
        "status": "idle",
        "alerts_fetched": len(alerts),
        "investigations_created": created,
        "total_runs": state["total_runs"] + 1,
        "total_created": state["total_created"] + created,
    }
    if latest_ts:
        update_fields["last_timestamp"] = latest_ts
    update_state(db, **update_fields)

    print(f"[Poller] Results: {created} created, {duplicates} duplicates, "
          f"{no_match} no policy match, {skipped} skipped")

    for r in results:
        if r.outcome.value == "created":
            print(f"  ✓ {r}")


def main():
    parser = argparse.ArgumentParser(description="Poll Wazuh alerts and create investigations")
    parser.add_argument("--hours", type=int, default=24,
                        help="Initial lookback window when no watermark exists (default: 24)")
    parser.add_argument("--loop", action="store_true",
                        help="Run continuously instead of once")
    parser.add_argument("--interval", type=int, default=60,
                        help="Seconds between polls in loop mode (default: 60)")
    parser.add_argument("--reset", action="store_true",
                        help="Clear the watermark and exit")
    args = parser.parse_args()

    # Initialize database
    print("[Poller] Connecting to MySQL...")
    db = Database()
    db.connect()
    db.init_tables()

    if args.reset:
        clear_watermark(db)
        db.close()
        return

    # Policy engine
    print("[Poller] Loading policy engine...")
    engine = PolicyEngine(db)
    engine.seed_defaults()

    policies = engine.list_policies(enabled_only=True)
    print(f"[Poller] {len(policies)} enabled policies:")
    for p in policies:
        print(f"  • {p['name']} (priority={p['priority']})")

    manager = InvestigationManager(db, engine)

    # Wazuh connection
    print("[Poller] Connecting to Wazuh Indexer...")
    receiver = create_receiver()

    try:
        info = receiver._client.info()
        print(f"[Poller] Connected to Wazuh Indexer: {info.get('cluster_name', '?')} "
              f"(v{info.get('version', {}).get('number', '?')})")
    except Exception as e:
        print(f"[Poller] ERROR: Cannot reach Wazuh Indexer: {e}")
        update_state(db, status="error",
                     error_message=f"Cannot reach Wazuh Indexer: {e}")
        db.close()
        return

    print("[Poller] Wazuh Indexer is reachable.")

    if args.loop:
        print(f"[Poller] Loop mode (every {args.interval}s). Ctrl+C to stop.\n")
        try:
            while True:
                run_once(db, receiver, manager, initial_hours=args.hours)
                print(f"[Poller] Sleeping {args.interval}s...\n")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            update_state(db, status="idle")
            print("\n[Poller] Stopped.")
    else:
        run_once(db, receiver, manager, initial_hours=args.hours)

    db.close()
    print("[Poller] Done.")


if __name__ == "__main__":
    main()
