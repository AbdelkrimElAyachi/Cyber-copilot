"""
System router — poller management and system status.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from poller_service import PollerService
from api.dependencies import get_poller_service

router = APIRouter(prefix="/poller", tags=["poller"])


# ── Request schemas ─────────────────────────────────────────────────────


class PollerStartRequest(BaseModel):
    interval: int = 60
    lookback_hours: int = 24


class PollerRunOnceRequest(BaseModel):
    lookback_hours: int = 24


# ── Endpoints ───────────────────────────────────────────────────────────


@router.get("/status")
def get_poller_status(
    poller: PollerService = Depends(get_poller_service),
):
    """Return the current poller status, configuration, and stats."""
    return poller.get_status()


@router.post("/start")
def start_poller(
    body: PollerStartRequest,
    poller: PollerService = Depends(get_poller_service),
):
    """Start the alert polling loop with the given configuration."""
    return poller.start(
        interval=body.interval,
        lookback_hours=body.lookback_hours,
    )


@router.post("/stop")
def stop_poller(
    poller: PollerService = Depends(get_poller_service),
):
    """Stop the alert polling loop."""
    return poller.stop()


@router.post("/run-once")
def run_once(
    body: PollerRunOnceRequest,
    poller: PollerService = Depends(get_poller_service),
):
    """Trigger a single poll run (synchronous)."""
    return poller.run_once(lookback_hours=body.lookback_hours)


@router.post("/reset")
def reset_watermark(
    poller: PollerService = Depends(get_poller_service),
):
    """Clear the watermark so the next poll starts fresh."""
    return poller.reset_watermark()


class PollerConfigRequest(BaseModel):
    interval: int = 60
    lookback_hours: int = 24


@router.patch("/config")
def update_config(
    body: PollerConfigRequest,
    poller: PollerService = Depends(get_poller_service),
):
    """Save poller configuration without starting or stopping."""
    return poller.save_config(
        interval=body.interval,
        lookback_hours=body.lookback_hours,
    )
