"""Tools package for the AI Investigator."""

from __future__ import annotations

import os
from typing import Optional, TYPE_CHECKING

from .base import Tool
from .wazuh_tools import SearchAlertsTool, CountAlertsTool, GetAlertDetailsTool
from .database_tools import (
    SearchInvestigationsTool,
    CountInvestigationsTool,
    GetInvestigationTool,
    GetInvestigationEvidenceTool,
    GetInvestigationAnalysisTool,
    SearchAssetsTool,
    GetAssetTool,
)
from .threat_intel_tools import CheckIPReputationTool

if TYPE_CHECKING:
    from database import Database
    from alert_receiver import AlertReceiver

__all__ = [
    "Tool",
    "SearchAlertsTool",
    "CountAlertsTool",
    "GetAlertDetailsTool",
    "SearchInvestigationsTool",
    "CountInvestigationsTool",
    "GetInvestigationTool",
    "GetInvestigationEvidenceTool",
    "GetInvestigationAnalysisTool",
    "SearchAssetsTool",
    "GetAssetTool",
    "CheckIPReputationTool",
    "build_default_tools",
]


def build_default_tools(
    db: "Database", alert_receiver: Optional["AlertReceiver"] = None
) -> dict[str, Tool]:
    """Build the standard read-only tool set shared by the AI Investigator
    and the chat assistant.

    Deliberately does not — and must not — include anything that reads the
    ``users`` table. There is no tool for it at all, so nothing built here
    can expose account data, regardless of what an LLM asks for.
    """
    tools: dict[str, Tool] = {}

    # Wazuh tools need a live receiver; unavailable if Wazuh isn't reachable.
    if alert_receiver is not None:
        tools["search_alerts"] = SearchAlertsTool(alert_receiver)
        tools["count_alerts"] = CountAlertsTool(alert_receiver)
        tools["get_alert_details"] = GetAlertDetailsTool(alert_receiver)

    # Platform database tools (investigations, evidence, analysis, assets).
    tools["search_investigations"] = SearchInvestigationsTool(db)
    tools["count_investigations"] = CountInvestigationsTool(db)
    tools["get_investigation"] = GetInvestigationTool(db)
    tools["get_investigation_evidence"] = GetInvestigationEvidenceTool(db)
    tools["get_investigation_analysis"] = GetInvestigationAnalysisTool(db)
    tools["search_assets"] = SearchAssetsTool(db)
    tools["get_asset"] = GetAssetTool(db)

    # External IP reputation lookup. Silently omitted (rather than added
    # broken) when no API key is configured, so the LLM never sees a tool
    # it can't actually use.
    if os.getenv("ABUSEIPDB_API_KEY"):
        tools["check_ip_reputation"] = CheckIPReputationTool()

    return tools
