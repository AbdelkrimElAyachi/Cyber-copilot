"""
API Dependencies — shared services and dependency injection providers.

Provides initialized instances of Database, PolicyEngine, and
InvestigationManager for FastAPI route handlers, along with application
lifecycle hooks (startup and shutdown).

Usage:
    from fastapi import Depends
    from api.dependencies import get_db, get_policy_engine, get_investigation_manager

    @router.get("/policies")
    def list_policies(engine: PolicyEngine = Depends(get_policy_engine)):
        return engine.list_policies()
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from database import Database
from investigation_manager import InvestigationManager
from investigation_policy import PolicyEngine


# ── Environment & Configuration ─────────────────────────────────────────

load_dotenv()

_MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
_MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
_MYSQL_USER = os.getenv("MYSQL_USER", "root")
_MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
_MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "cyber_copilot")


# ── Service Instances ───────────────────────────────────────────────────

db = Database(
    host=_MYSQL_HOST,
    port=_MYSQL_PORT,
    user=_MYSQL_USER,
    password=_MYSQL_PASSWORD,
    database=_MYSQL_DATABASE,
)

policy_engine = PolicyEngine(db)

investigation_manager = InvestigationManager(db, policy_engine)


# ── Dependency Providers ────────────────────────────────────────────────

def get_db() -> Database:
    """Return the shared Database instance."""
    return db


def get_policy_engine() -> PolicyEngine:
    """Return the shared PolicyEngine instance."""
    return policy_engine


def get_investigation_manager() -> InvestigationManager:
    """Return the shared InvestigationManager instance."""
    return investigation_manager


# ── Lifecycle Hooks ─────────────────────────────────────────────────────

def startup() -> None:
    """Initialize database connection and ensure tables exist."""
    db.connect()
    db.init_tables()


def shutdown() -> None:
    """Close the database connection."""
    db.close()
