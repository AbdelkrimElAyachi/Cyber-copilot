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

# AI Investigator — LLM provider settings. "local" (Ollama) needs no key;
# "api" works with any OpenAI-compatible endpoint (OpenAI, Groq, etc.).
_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "local")
_LLM_BASE_URL = os.getenv("LLM_BASE_URL")
_LLM_MODEL = os.getenv("LLM_MODEL")
_LLM_API_KEY = os.getenv("LLM_API_KEY") or None
_LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
_LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))


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

# AlertReceiver and AIInvestigator are created lazily during startup —
# Wazuh / the LLM may not be reachable yet.  The PollerService handles
# a missing receiver gracefully; a missing investigator just means
# investigations stay QUEUED until manually run.
alert_receiver = None  # type: ignore[assignment]
ai_investigator = None  # type: ignore[assignment]
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


def get_alert_receiver():
    """Return the shared AlertReceiver instance, or None if unavailable."""
    return alert_receiver


def get_ai_investigator():
    """Return the shared AIInvestigator instance, or None if unavailable."""
    return ai_investigator


# ── Lifecycle Hooks ─────────────────────────────────────────────────────

def startup() -> None:
    """Initialize database, seed defaults, and set up the poller."""
    global poller_service, alert_receiver, ai_investigator

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
    alert_receiver = receiver

    # Try to create the AI Investigator. The provider (local/api) and
    # model are fully driven by env config — investigation logic itself
    # doesn't know or care which one is in use.
    investigator = None
    try:
        from ai_investigator.llm import create_provider
        from ai_investigator.investigator import AIInvestigator

        llm_kwargs: dict = {"temperature": _LLM_TEMPERATURE, "max_tokens": _LLM_MAX_TOKENS}
        if _LLM_BASE_URL:
            llm_kwargs["base_url"] = _LLM_BASE_URL
        if _LLM_MODEL:
            llm_kwargs["model"] = _LLM_MODEL
        if _LLM_PROVIDER == "api":
            llm_kwargs["api_key"] = _LLM_API_KEY

        llm = create_provider(_LLM_PROVIDER, **llm_kwargs)
        investigator = AIInvestigator(llm=llm, db=db, alert_receiver=receiver)
        logger.info(
            "AI Investigator ready (provider=%s, model=%s)",
            _LLM_PROVIDER, llm_kwargs.get("model", "<default>"),
        )
    except Exception as e:
        logger.warning("AI Investigator disabled: %s", e)
    ai_investigator = investigator

    poller_service = PollerService(
        db=db,
        policy_engine=policy_engine,
        investigation_manager=investigation_manager,
        alert_receiver=receiver,
        ai_investigator=investigator,
    )
    poller_service.load_config()


def shutdown() -> None:
    """Stop the poller and close the database."""
    if poller_service is not None and poller_service.is_running:
        poller_service.stop()
    db.close()
