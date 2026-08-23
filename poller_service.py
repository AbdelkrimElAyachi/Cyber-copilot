"""
Poller Service — manages the Wazuh alert polling lifecycle.

Runs the alert polling loop in a background thread, controllable
via the API. Each poll fetches new alerts from the Wazuh Indexer,
evaluates them against investigation policies, and creates
investigations for matching alerts.

The polling state (watermark, stats) is stored in MySQL so it
persists across restarts and is visible from the frontend.
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from alert_receiver import AlertReceiver
from database import Database, new_id
from investigation_manager import InvestigationManager
from investigation_policy import PolicyEngine

logger = logging.getLogger("poller")

POLLER_NAME = "wazuh_alert_poller"


class PollerService:
    """Manages the alert polling lifecycle in a background thread.

    Thread-safe: the polling loop runs on a daemon thread and
    communicates state through the database.  Start / stop can be
    called safely from any request thread.
    """

    def __init__(
        self,
        db: Database,
        policy_engine: PolicyEngine,
        investigation_manager: InvestigationManager,
        alert_receiver: Optional[AlertReceiver] = None,
    ) -> None:
        self._db = db
        self._engine = policy_engine
        self._manager = investigation_manager
        self._receiver = alert_receiver
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._interval: int = 60
        self._lookback_hours: int = 24

    # ── Public API ──────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """True when the background polling thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        interval: int = 60,
        lookback_hours: int = 24,
    ) -> dict[str, Any]:
        """Start the polling loop in a background thread."""
        if self.is_running:
            return {
                "status": "already_running",
                "message": "Poller is already running.",
            }

        if self._receiver is None:
            return {
                "status": "error",
                "message": "Wazuh Indexer is not configured.",
            }

        # Verify Wazuh connectivity before starting
        try:
            self._receiver._client.info()
        except Exception as e:
            return {
                "status": "error",
                "message": f"Cannot reach Wazuh Indexer: {e}",
            }

        self._interval = interval
        self._lookback_hours = lookback_hours

        # Persist config to database
        self._update_state(
            interval_seconds=interval,
            lookback_hours=lookback_hours,
        )

        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._run_loop,
            name="alert-poller",
            daemon=True,
        )
        self._thread.start()

        logger.info(
            "Poller started (interval=%ds, lookback=%dh)",
            interval,
            lookback_hours,
        )
        return {
            "status": "started",
            "interval": interval,
            "lookback_hours": lookback_hours,
        }

    def stop(self) -> dict[str, Any]:
        """Stop the polling loop."""
        if not self.is_running:
            return {"status": "not_running", "message": "Poller is not running."}

        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        self._thread = None

        self._update_state(status="stopped")
        logger.info("Poller stopped")
        return {"status": "stopped"}

    def run_once(self, lookback_hours: int = 24) -> dict[str, Any]:
        """Run a single poll synchronously and return results."""
        if self._receiver is None:
            return {"status": "error", "message": "Wazuh Indexer is not configured."}
        return self._poll(lookback_hours)

    def reset_watermark(self) -> dict[str, Any]:
        """Clear the watermark so the next poll starts fresh."""
        self._db.execute(
            "UPDATE poller_state SET last_timestamp = NULL, total_runs = 0, "
            "total_created = 0, alerts_fetched = 0, investigations_created = 0, "
            "error_message = NULL, status = 'idle' "
            "WHERE poller_name = %s",
            (POLLER_NAME,),
        )
        return {"status": "reset", "message": "Watermark cleared."}

    def get_status(self) -> dict[str, Any]:
        """Return current poller status, config, and stats."""
        state = self._get_or_create_state()
        return {
            **state,
            "is_running": self.is_running,
            "interval": state.get("interval_seconds", self._interval),
            "lookback_hours": state.get("lookback_hours", self._lookback_hours),
            "wazuh_configured": self._receiver is not None,
        }

    def load_config(self) -> None:
        """Load saved config from the database into memory."""
        state = self._get_or_create_state()
        self._interval = state.get("interval_seconds", 60) or 60
        self._lookback_hours = state.get("lookback_hours", 24) or 24

    def save_config(
        self, interval: int = 60, lookback_hours: int = 24
    ) -> dict[str, Any]:
        """Save config to DB and update in-memory values."""
        self._interval = interval
        self._lookback_hours = lookback_hours
        self._update_state(
            interval_seconds=interval,
            lookback_hours=lookback_hours,
        )
        return {
            "status": "saved",
            "interval": interval,
            "lookback_hours": lookback_hours,
        }

    # ── Background loop ─────────────────────────────────────────────

    def _run_loop(self) -> None:
        """Main polling loop — runs in a background thread."""
        logger.info("Poller loop started")
        while not self._stop_event.is_set():
            try:
                result = self._poll(self._lookback_hours)
                logger.info(
                    "Poll complete: %d fetched, %d created",
                    result.get("alerts_fetched", 0),
                    result.get("created", 0),
                )
            except Exception as e:
                logger.error("Poller error: %s", e)
                self._update_state(status="error", error_message=str(e))

            # Wait for interval or until stop is signalled.
            self._stop_event.wait(self._interval)

        logger.info("Poller loop stopped")

    def _poll(self, initial_hours: int) -> dict[str, Any]:
        """Fetch and process new alerts since the watermark."""
        state = self._get_or_create_state()
        watermark = state.get("last_timestamp")

        self._update_state(
            status="running",
            error_message=None,
            last_run_at=datetime.now(),
        )

        # Determine start time
        if watermark:
            from_time = _parse_timestamp(watermark)
            hours_ago = datetime.now(timezone.utc) - timedelta(hours=initial_hours)
            if hours_ago < from_time:
                from_time = hours_ago
        else:
            from_time = datetime.now(timezone.utc) - timedelta(hours=initial_hours)

        # Fetch alerts from Wazuh
        try:
            alerts = self._receiver.get_alerts(
                from_time=from_time, limit=500, sort_order="asc"
            )
        except Exception as e:
            self._update_state(status="error", error_message=str(e))
            return {"error": str(e), "alerts_fetched": 0, "created": 0}

        if not alerts:
            state = self._get_or_create_state()
            self._update_state(
                status="idle", alerts_fetched=0, investigations_created=0,
                total_runs=state["total_runs"] + 1,
            )
            return {"alerts_fetched": 0, "created": 0}

        # Process alerts through the investigation manager
        results = self._manager.process_alerts(alerts)

        # Find the latest alert timestamp for the watermark
        latest_ts = None
        for alert in reversed(alerts):
            ts = alert.get("timestamp")
            if ts:
                latest_ts = ts
                break

        # Count outcomes
        created = sum(1 for r in results if r.outcome.value == "created")
        duplicates = sum(1 for r in results if r.outcome.value == "duplicate")
        no_match = sum(1 for r in results if r.outcome.value == "no_match")
        skipped = sum(1 for r in results if r.outcome.value == "skipped")

        # Update state in database
        update_fields: dict[str, Any] = {
            "status": "idle",
            "alerts_fetched": len(alerts),
            "investigations_created": created,
            "total_runs": state["total_runs"] + 1,
            "total_created": state["total_created"] + created,
        }
        if latest_ts:
            update_fields["last_timestamp"] = latest_ts
        self._update_state(**update_fields)

        return {
            "alerts_fetched": len(alerts),
            "created": created,
            "duplicates": duplicates,
            "no_match": no_match,
            "skipped": skipped,
        }

    # ── State helpers ───────────────────────────────────────────────

    def _get_or_create_state(self) -> dict[str, Any]:
        """Get the poller state row, creating it if needed."""
        row = self._db.fetchone(
            "SELECT * FROM poller_state WHERE poller_name = %s",
            (POLLER_NAME,),
        )
        if row:
            return row

        state_id = new_id()
        self._db.execute(
            "INSERT INTO poller_state (id, poller_name, status) "
            "VALUES (%s, %s, %s)",
            (state_id, POLLER_NAME, "idle"),
        )
        return self._db.fetchone(
            "SELECT * FROM poller_state WHERE id = %s",
            (state_id,),
        )

    def _update_state(self, **fields: Any) -> None:
        """Update one or more fields on the poller state row."""
        if not fields:
            return
        set_parts = []
        values: list[Any] = []
        for key, val in fields.items():
            set_parts.append(f"{key} = %s")
            values.append(val)
        values.append(POLLER_NAME)
        self._db.execute(
            f"UPDATE poller_state SET {', '.join(set_parts)} "
            f"WHERE poller_name = %s",
            tuple(values),
        )


# ── Helpers ─────────────────────────────────────────────────────────────


def _parse_timestamp(ts: str) -> datetime:
    """Parse ISO-8601 timestamps, handling offsets with or without colons.

    Python 3.10's ``fromisoformat`` doesn't accept ``+0100`` — only
    ``+01:00``.  Wazuh timestamps often use the no-colon format.
    """
    ts = re.sub(r"([+-])(\d{2})(\d{2})$", r"\1\2:\3", ts)
    return datetime.fromisoformat(ts)
