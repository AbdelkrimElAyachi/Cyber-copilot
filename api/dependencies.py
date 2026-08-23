"""
API Dependencies — shared services and dependency injection providers.

Provides initialized instances of Database, PolicyEngine,
InvestigationManager, AlertReceiver, and PollerService for FastAPI
route handlers, along with application lifecycle hooks.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

from database import Database
from investigation_manager import InvestigationManager
from investigation_policy import PolicyEngine
from poller_service import PollerService

logger = logging.getLogger(__name__)


# ── Environment & Configuration ─────────────────────────────────────────

load_dotenv()

_MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
_MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
_MYSQL_USER = os.getenv("MYSQL_USER", "root")
_MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
_MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "cyber_copilot")

_WAZUH_HOST = os.getenv("WAZUH_INDEXER_HOST", "localhost")
_WAZUH_PORT = int(os.getenv("WAZUH_INDEXER_PORT", "9200"))
_WAZUH_USER = os.getenv("WAZUH_INDEXER_USERNAME", "admin")
_WAZUH_PASSWORD = os.getenv("WAZUH_INDEXER_PASSWORD", "admin")
_WAZUH_VERIFY_SSL = os.getenv("WAZUH_INDEXER_VERIFY_SSL", "false").lower() == "true"


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

# AlertReceiver is created lazily during startup — Wazuh may not be
# reachable yet.  The PollerService handles this gracefully.
poller_service: PollerService = None  # type: ignore[assignment]


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


def get_poller_service() -> PollerService:
    """Return the shared PollerService instance."""
    return poller_service


# ── Lifecycle Hooks ─────────────────────────────────────────────────────

def startup() -> None:
    """Initialize database, seed defaults, and set up the poller."""
    global poller_service

    db.connect()
    db.init_tables()

    # Seed default investigation policies if none exist.
    policy_engine.seed_defaults()

    # Try to create the AlertReceiver.  If Wazuh is unreachable, the
    # poller will start without it and report the error when triggered.
    receiver = None
    try:
        from alert_receiver import AlertReceiver

        receiver = AlertReceiver(
            host=_WAZUH_HOST,
            port=_WAZUH_PORT,
            username=_WAZUH_USER,
            password=_WAZUH_PASSWORD,
            verify_ssl=_WAZUH_VERIFY_SSL,
        )
        logger.info("AlertReceiver created for %s:%s", _WAZUH_HOST, _WAZUH_PORT)
    except Exception as e:
        logger.warning("Could not create AlertReceiver: %s", e)

    poller_service = PollerService(
        db=db,
        policy_engine=policy_engine,
        investigation_manager=investigation_manager,
        alert_receiver=receiver,
    )
    poller_service.load_config()


def shutdown() -> None:
    """Stop the poller and close the database."""
    if poller_service is not None and poller_service.is_running:
        poller_service.stop()
    db.close()
