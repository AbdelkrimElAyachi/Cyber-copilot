"""
System router — health checks and poller status.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from database import Database
from api.dependencies import get_db

router = APIRouter(tags=["system"])


@router.get("/poller/status")
def get_poller_status(db: Database = Depends(get_db)):
    """Return the current state of the alert poller."""
    row = db.fetchone(
        "SELECT * FROM poller_state WHERE poller_name = %s",
        ("wazuh_alert_poller",),
    )
    if not row:
        return {
            "status": "not_started",
            "message": "Poller has never been run. Start it with: python poll_alerts.py",
        }
    return row
