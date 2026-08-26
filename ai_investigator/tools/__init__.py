"""Tools package for the AI Investigator."""

from .base import Tool
from .wazuh_tools import SearchAlertsTool, GetAlertDetailsTool
from .database_tools import (
    SearchInvestigationsTool,
    GetInvestigationTool,
    GetInvestigationEvidenceTool,
    GetInvestigationAnalysisTool,
    SearchAssetsTool,
    GetAssetTool,
)

__all__ = [
    "Tool",
    "SearchAlertsTool",
    "GetAlertDetailsTool",
    "SearchInvestigationsTool",
    "GetInvestigationTool",
    "GetInvestigationEvidenceTool",
    "GetInvestigationAnalysisTool",
    "SearchAssetsTool",
    "GetAssetTool",
]
